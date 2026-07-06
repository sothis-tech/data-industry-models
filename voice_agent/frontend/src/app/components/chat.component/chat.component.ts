import { Component, OnInit, OnDestroy, Renderer2 } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MicService } from '../../services/mic.service';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './chat.component.html',
  styleUrls: ['./chat.component.css'],
  providers: [MicService]
})
export class ChatComponent implements OnInit, OnDestroy {
  messages: { from: 'user' | 'bot', text: string }[] = [];
  isTalking = false;
  isProcessing = false;
  isDarkMode = false;

  private audioCtx!: AudioContext;
  private processor!: ScriptProcessorNode;
  private stream!: MediaStream;
  private subs: any;

  private monitorGain?: GainNode;

  // Acumulador de muestras y tamaño de frame dinámico (20 ms)
  private pendingSamples: Int16Array = new Int16Array(0);
  private frameSamples = 960; // se recalcula con sampleRate real (≈ 48kHz * 0.02)

  constructor(private micService: MicService, private renderer: Renderer2) {}

  ngOnInit(): void {
    const savedTheme = localStorage.getItem('darkMode');
    this.isDarkMode = savedTheme === 'true';
    this.applyDarkModeClass(this.isDarkMode);

    this.micService.connect();
    this.subs = this.micService.getMessages().subscribe(msg => {
      this.isProcessing = false;
      
      // Si hay transcript, agregarlo/actualizarlo
      if (msg.user) {
        // Buscar si ya existe un mensaje del usuario sin respuesta
        const existingUserMsg = this.messages.findIndex(m => m.from === 'user' && !this.messages[this.messages.indexOf(m) + 1]);
        if (existingUserMsg >= 0) {
          // Actualizar mensaje existente
          this.messages[existingUserMsg].text = msg.user;
        } else {
          // Agregar nuevo mensaje del usuario
          this.messages.push({ from: 'user', text: msg.user });
        }
      }
      
      // Si hay respuesta del bot, agregarla/actualizarla
      if (msg.bot) {
        // Reproducir audio si existe
        if (msg.audio) {
          this.playAudio(msg.audio);
        }

        // Buscar el último mensaje del usuario y agregar la respuesta después
        const lastUserIndex = this.messages.map((m, i) => m.from === 'user' ? i : -1).filter(i => i >= 0).pop();
        if (lastUserIndex !== undefined) {
          // Verificar si ya hay una respuesta del bot después de este mensaje
          if (this.messages[lastUserIndex + 1]?.from === 'bot') {
            // Actualizar respuesta existente
            this.messages[lastUserIndex + 1].text = msg.bot;
          } else {
            // Agregar nueva respuesta
            this.messages.push({ from: 'bot', text: msg.bot });
          }
        } else {
          // Si no hay mensaje del usuario, agregar la respuesta de todas formas
          this.messages.push({ from: 'bot', text: msg.bot });
        }
      }
    });
  }

  toggleDarkMode() {
    this.isDarkMode = !this.isDarkMode;
    localStorage.setItem('darkMode', this.isDarkMode.toString());
    this.applyDarkModeClass(this.isDarkMode);
  }

  private applyDarkModeClass(isDark: boolean): void {
    if (isDark) this.renderer.addClass(document.body, 'dark-mode');
    else this.renderer.removeClass(document.body, 'dark-mode');
  }

  startCapture(): void {
    this.isTalking = true;
    navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
        channelCount: 1
      }
    }).then(stream => {
      // AudioContext a tasa nativa (≃ 48 kHz en la mayoría de navegadores)
      this.audioCtx = new AudioContext();
      this.frameSamples = Math.round(this.audioCtx.sampleRate * 0.02); // 20 ms
      this.stream = stream;

      const source = this.audioCtx.createMediaStreamSource(stream);
      this.processor = this.audioCtx.createScriptProcessor(1024, 1, 1);

      // Conectamos el micro al processor (para empaquetar y enviar)
      source.connect(this.processor);

      // Monitor local: source -> gain -> destination
      this.monitorGain = this.audioCtx.createGain();
      this.monitorGain.gain.value = 1.0;
      source.connect(this.monitorGain);
      this.monitorGain.connect(this.audioCtx.destination);

      // IMPORTANTE: El processor DEBE estar conectado a algo para que funcione
      // Lo conectamos a un GainNode con volumen 0 para evitar eco pero activar el procesamiento
      const silentGain = this.audioCtx.createGain();
      silentGain.gain.value = 0; // Sin sonido
      source.connect(this.processor);
      this.processor.connect(silentGain);
      silentGain.connect(this.audioCtx.destination); // Necesita estar conectado a destination

      this.processor.onaudioprocess = e => {
        const input = e.inputBuffer.getChannelData(0);
        const int16 = new Int16Array(input.length);
        for (let i = 0; i < input.length; i++) {
          const s = Math.max(-1, Math.min(1, input[i]));
          int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        // Acumula y envía en frames exactos de 20 ms (≈ 960 muestras @ 48k)
        this.pendingSamples = this.concatInt16(this.pendingSamples, int16) as Int16Array<ArrayBuffer>;
        while (this.pendingSamples.length >= this.frameSamples) {
          const frame = this.pendingSamples.subarray(0, this.frameSamples);
          this.micService.sendAudioChunk(frame.buffer as ArrayBuffer); // 20 ms -> ~1920 bytes
          this.pendingSamples = this.pendingSamples.subarray(this.frameSamples);
        }
      };
    }).catch(err => {
      console.error('Error accediendo al micrófono:', err);
      this.isTalking = false;
    });
  }

  stopCapture(): void {
    this.isTalking = false;
    this.isProcessing = true;

    // Flush final de lo que quede (< 20 ms)
    if (this.pendingSamples.length > 0) {
      const mod = this.pendingSamples.length % this.frameSamples;
      const pad = mod === 0 ? 0 : this.frameSamples - mod;
      const padded = new Int16Array(this.pendingSamples.length + pad);
      padded.set(this.pendingSamples, 0);
      this.micService.sendAudioChunk(padded.buffer);
      this.pendingSamples = new Int16Array(0);
    }

    // Apaga el monitor
    this.monitorGain?.disconnect();
    this.monitorGain = undefined;

    this.processor?.disconnect();
    this.stream?.getTracks().forEach(t => t.stop());
    this.audioCtx?.close();
    this.micService.sendEnd();
  }

  ngOnDestroy(): void {
    try { this.stopCapture(); } catch {}
    this.subs?.unsubscribe();
    this.micService.disconnect();
  }

  private concatInt16(a: Int16Array, b: Int16Array): Int16Array {
    if (a.length === 0) return b;
    const totalLength = a.length + b.length;
    const result = new Int16Array(totalLength);
    result.set(a, 0);
    result.set(b, a.length);
    return result;
  }

  private playAudio(base64Audio: string): void {
    try {
      const binaryString = atob(base64Audio);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: 'audio/wav' });
      const audioUrl = URL.createObjectURL(blob);
      const audio = new Audio(audioUrl);
      
      // Reproducir
      audio.play().catch(e => console.error("Error reproduciendo audio:", e));
      
      // Liberar memoria al terminar
      audio.onended = () => URL.revokeObjectURL(audioUrl);
    } catch (e) {
      console.error("Error procesando audio base64:", e);
    }
  }
}

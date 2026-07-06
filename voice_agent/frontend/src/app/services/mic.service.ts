import { Injectable } from '@angular/core';
import { Observable, Subject } from 'rxjs';

export interface ChatMessage {
  event: 'transcription';
  user?: string;
  bot?: string;
  audio?: string; // Nuevo campo para audio en base64
  debugAudioUrl?: string;
  meta?: {
    session_id?: string;
    segment_duration_sec?: number;
    segment_rms?: number;
    debug_segment_path?: string | null;
  };
}

@Injectable()
export class MicService {
  private socket!: WebSocket;
  private messagesSubject = new Subject<ChatMessage>();
  private objectUrls: string[] = [];
  private isDisconnecting = false;
  private reconnectTimeout?: number;
  private reconnectAttempts = 0;
  private readonly maxReconnectAttempts = 5;
  private readonly reconnectDelay = 1000; // 1 segundo inicial

  connect(): void {
    if (this.socket?.readyState === WebSocket.OPEN) return;
    
    // Limpiar intento de reconexión previo
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = undefined;
    }

    this.isDisconnecting = false;
    this.reconnectAttempts = 0;

    // Backend voice-agent en 8000; agente del compañero en 8001
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const backendPort = 8000;
    let wsUrl: string;

    if (window.location.hostname === 'localhost' && window.location.port === '4200') {
      wsUrl = `${protocol}//localhost:${backendPort}/ws/audio`;
      console.log('Modo local - conectando al backend en puerto', backendPort);
    } else {
      wsUrl = `${protocol}//${window.location.hostname}:${backendPort}/ws/audio`;
      console.log('Modo VM/producción - conectando al backend en', window.location.hostname + ':' + backendPort);
    }
    
    console.log('Conectando a WebSocket:', wsUrl);
    this.socket = new WebSocket(wsUrl);
    this.socket.binaryType = 'arraybuffer';

    this.socket.onopen = () => {
      console.log('WebSocket conectado');
      this.reconnectAttempts = 0; // Resetear contador de reconexiones
    };

    this.socket.onerror = (error) => {
      console.error('Error en WebSocket:', error);
    };

    this.socket.onmessage = ({ data }) => {
      console.log('Mensaje recibido del servidor:', data);
      try {
        const payload = JSON.parse(data);
        console.log('Payload parseado:', payload);
        let debugAudioUrl: string | undefined;

        if (payload.debug_audio_b64) {
          const blob = this.base64WavToBlob(payload.debug_audio_b64);
          debugAudioUrl = URL.createObjectURL(blob);
          this.objectUrls.push(debugAudioUrl);
        }

        this.messagesSubject.next({
          event: 'transcription',
          user: payload.transcript,
          bot: payload.response,
          audio: payload.audio, // Pasar audio al componente
          debugAudioUrl,
          meta: payload.meta,
        });
      } catch (err) {
        console.error('Error parseando mensaje:', err);
      }
    };

    this.socket.onclose = (event) => {
      console.log('WebSocket cerrado', { code: event.code, reason: event.reason, wasClean: event.wasClean });
      
      // Solo completar el Observable si fue una desconexión explícita
      if (this.isDisconnecting) {
        console.log('Desconexión explícita - completando Observable');
        this.messagesSubject.complete();
      } else {
        // Reconexión automática si no fue una desconexión explícita
        console.log('Cierre inesperado - intentando reconectar...');
        this.attemptReconnect();
      }
      
      this.revokeAllUrls();
    };
  }

  private attemptReconnect(): void {
    if (this.isDisconnecting) return;
    
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Máximo de intentos de reconexión alcanzado');
      this.messagesSubject.complete();
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1); // Backoff exponencial
    
    console.log(`Reintentando conexión en ${delay}ms (intento ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    this.reconnectTimeout = window.setTimeout(() => {
      this.connect();
    }, delay);
  }

  sendAudioChunk(chunk: ArrayBuffer): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(chunk);
    } else {
      console.warn('WebSocket no está abierto, no se puede enviar audio. Estado:', this.socket?.readyState);
      // Intentar reconectar si no está conectado
      if (this.socket?.readyState === WebSocket.CLOSED && !this.isDisconnecting) {
        console.log('WebSocket cerrado - intentando reconectar...');
        this.connect();
      }
    }
  }

  sendEnd(): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send('__END__');
    }
  }

  getMessages(): Observable<ChatMessage> {
    return this.messagesSubject.asObservable();
  }

  disconnect(): void {
    this.isDisconnecting = true;
    
    // Limpiar timeout de reconexión
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = undefined;
    }
    
    try { 
      this.sendEnd(); 
    } catch (e) {
      console.warn('Error enviando __END__:', e);
    }
    
    try { 
      this.socket?.close(); 
    } catch (e) {
      console.warn('Error cerrando WebSocket:', e);
    }
    
    this.revokeAllUrls();
    this.messagesSubject.complete();
  }

  private base64WavToBlob(b64: string): Blob {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new Blob([bytes], { type: 'audio/wav' });
  }

  private revokeAllUrls(): void {
    this.objectUrls.forEach(url => URL.revokeObjectURL(url));
    this.objectUrls = [];
  }
}

import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';
import { ChatComponent } from './app/components/chat.component/chat.component';

bootstrapApplication(ChatComponent)
  .catch((err) => console.error(err));

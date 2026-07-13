import { bootstrapApplication } from "@angular/platform-browser";
import { provideHttpClient, withInterceptors } from "@angular/common/http";
import { provideRouter } from "@angular/router";
import { AppComponent } from "./app/app.component";
import { routes } from "./app/app.routes";
import { apiBaseInterceptor } from "./app/core/api-base.interceptor";

bootstrapApplication(AppComponent, {
  providers: [provideRouter(routes), provideHttpClient(withInterceptors([apiBaseInterceptor]))]
}).catch((error) => console.error(error));
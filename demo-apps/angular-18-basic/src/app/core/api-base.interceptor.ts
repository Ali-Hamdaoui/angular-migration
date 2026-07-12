import { HttpInterceptorFn } from "@angular/common/http";
import { environment } from "../../environments/environment";

export const apiBaseInterceptor: HttpInterceptorFn = (request, next) => {
  const isRelativeApiCall = request.url.startsWith("/api/");
  const normalizedUrl = isRelativeApiCall ? request.url : `${environment.apiBaseUrl}${request.url.startsWith("/") ? request.url : `/${request.url}`}`;
  return next(request.clone({ url: normalizedUrl, setHeaders: { "X-Fixture-App": "angular-18-basic" } }));
};
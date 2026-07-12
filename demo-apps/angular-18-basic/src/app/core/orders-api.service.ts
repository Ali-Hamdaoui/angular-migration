import { HttpClient } from "@angular/common/http";
import { Injectable, inject } from "@angular/core";
import { Observable } from "rxjs";

export type OrderDraft = { customerName: string; quantity: number; rush: boolean };
export type OrderSummary = OrderDraft & { id: string; status: "queued" | "accepted" };

@Injectable({ providedIn: "root" })
export class OrdersApiService {
  private readonly http = inject(HttpClient);

  createOrder(draft: OrderDraft): Observable<OrderSummary> {
    return this.http.post<OrderSummary>("/orders", draft);
  }
}
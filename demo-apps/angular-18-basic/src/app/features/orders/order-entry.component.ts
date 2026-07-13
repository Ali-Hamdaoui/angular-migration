import { Component, inject } from "@angular/core";
import { FormBuilder, ReactiveFormsModule, Validators } from "@angular/forms";
import { OrdersApiService } from "../../core/orders-api.service";

@Component({
  selector: "amf-order-entry",
  standalone: true,
  imports: [ReactiveFormsModule],
  templateUrl: "./order-entry.component.html",
  styleUrl: "./order-entry.component.css"
})
export class OrderEntryComponent {
  private readonly fb = inject(FormBuilder);
  private readonly ordersApi = inject(OrdersApiService);
  submitted = false;

  orderForm = this.fb.nonNullable.group({
    customerName: ["", [Validators.required, Validators.minLength(3)]],
    quantity: [1, [Validators.required, Validators.min(1), Validators.max(10)]],
    rush: [false]
  });

  submit(): void {
    if (this.orderForm.invalid) {
      this.orderForm.markAllAsTouched();
      return;
    }
    this.ordersApi.createOrder(this.orderForm.getRawValue()).subscribe(() => {
      this.submitted = true;
    });
  }
}
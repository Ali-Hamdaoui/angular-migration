import { provideHttpClient } from "@angular/common/http";
import { ComponentFixture, TestBed } from "@angular/core/testing";
import { OrderEntryComponent } from "./order-entry.component";

describe("OrderEntryComponent", () => {
  let fixture: ComponentFixture<OrderEntryComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [OrderEntryComponent],
      providers: [provideHttpClient()]
    }).compileComponents();
    fixture = TestBed.createComponent(OrderEntryComponent);
    fixture.detectChanges();
  });

  it("starts with an invalid customer name", () => {
    expect(fixture.componentInstance.orderForm.valid).toBeFalse();
  });
});
import { Routes } from "@angular/router";
import { HomeComponent } from "./features/about/home.component";
import { AboutComponent } from "./features/about/about.component";

export const routes: Routes = [
  { path: "", pathMatch: "full", component: HomeComponent },
  { path: "orders", loadComponent: () => import("./features/orders/order-entry.component").then((m) => m.OrderEntryComponent) },
  { path: "about", component: AboutComponent },
  { path: "**", redirectTo: "" }
];
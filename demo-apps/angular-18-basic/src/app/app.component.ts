import { Component } from "@angular/core";
import { RouterLink, RouterOutlet } from "@angular/router";

@Component({
  selector: "amf-root",
  standalone: true,
  imports: [RouterLink, RouterOutlet],
  templateUrl: "./app.component.html",
  styleUrl: "./app.component.css"
})
export class AppComponent {
  title = "Angular 18 Basic Fixture";
}
import { Component } from "@angular/core";
import { environment } from "../../../environments/environment";

@Component({
  selector: "amf-about",
  standalone: true,
  template: `<section><h2>About</h2><p>API base: {{ apiBaseUrl }}</p><p>Fixture mode: {{ fixtureMode }}</p></section>`
})
export class AboutComponent {
  apiBaseUrl = environment.apiBaseUrl;
  fixtureMode = environment.featureFlags.fixtureMode;
}
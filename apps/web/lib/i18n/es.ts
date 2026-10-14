import { groq } from "./dicts/groq";
import { builder } from "./dicts/builder";
import { ollama } from "./dicts/ollama";
import { appointments } from "./dicts/appointments";
import { automations } from "./dicts/automations";
import { login } from "./dicts/login";
import type { Dictionary } from "./en";
import { core } from "./dicts/core";
import { home } from "./dicts/home";
import { clients } from "./dicts/clients";
import { agents } from "./dicts/agents";
import { channels } from "./dicts/channels";
import { social } from "./dicts/social";
import { settings } from "./dicts/settings";
import { playground } from "./dicts/playground";
import { portal } from "./dicts/portal";
import { inbox } from "./dicts/inbox";
import { tools } from "./dicts/tools";

// Spanish dictionary. Composed from the same modules; typed as Dictionary so it
// must mirror the exact shape of `en` (each area's `es` mirrors its own `en`).
export const es: Dictionary = {
  ...core.es,
  builder: builder.es,
  ollama: ollama.es,
  groq: groq.es,
  appointments: appointments.es,
  automations: automations.es,
  login: login.es,
  home: home.es,
  clients: clients.es,
  agents: agents.es,
  channels: channels.es,
  social: social.es,
  settings: settings.es,
  playground: playground.es,
  portal: portal.es,
  inbox: inbox.es,
  tools: tools.es,
};

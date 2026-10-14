import { groq } from "./dicts/groq";
import { builder } from "./dicts/builder";
import { ollama } from "./dicts/ollama";
import { appointments } from "./dicts/appointments";
import { automations } from "./dicts/automations";
import { login } from "./dicts/login";
// English dictionary (source of truth), composed from per-area modules under
// ./dicts. `es.ts` mirrors this exact shape. Access with dotted paths, e.g.
// t("nav.clients"), t("clients.list.title").
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

export const en = {
  ...core.en,
  builder: builder.en,
  ollama: ollama.en,
  groq: groq.en,
  appointments: appointments.en,
  automations: automations.en,
  login: login.en,
  home: home.en,
  clients: clients.en,
  agents: agents.en,
  channels: channels.en,
  social: social.en,
  settings: settings.en,
  playground: playground.en,
  portal: portal.en,
  inbox: inbox.en,
  tools: tools.en,
};

export type Dictionary = typeof en;

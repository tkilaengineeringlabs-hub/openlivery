"use client";
import { useState } from "react";
import { AgentBuilder } from "@/components/agent-builder/wizard";
import AdvancedCreate from "@/components/agent-builder/advanced-create";
import { useT } from "@/lib/i18n";
import "@/components/agent-builder/builder.css";

export default function NewAgentPage() {
  const t = useT();
  const [advanced, setAdvanced] = useState(false);
  return <><div className="builder-mode"><button type="button" className="button ghost" onClick={() => setAdvanced(!advanced)}>{t(advanced ? "builder.guided" : "builder.advanced")}</button></div>{advanced ? <AdvancedCreate /> : <AgentBuilder />}</>;
}

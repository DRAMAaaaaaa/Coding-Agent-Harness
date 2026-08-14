import { FormEvent, useLayoutEffect, useRef, useState } from "react";
import type { HarnessApi, ProviderProfile } from "../types";

interface ProviderSettingsProps {
  api: Pick<HarnessApi, "listProviders" | "createProvider" | "setSessionCredential">;
  providers: ProviderProfile[];
  selectedId: string;
  disabled: boolean;
  resetVersion: number;
  onProvidersChange(next: ProviderProfile[]): void;
  onSelect(id: string): void;
}

export function ProviderSettings({ api, providers, selectedId, disabled, onProvidersChange, onSelect }: ProviderSettingsProps) {
  const [open, setOpen] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [kind, setKind] = useState<ProviderProfile["kind"]>("deepseek");
  const [model, setModel] = useState("deepseek-chat");
  const openerRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  const close = (): void => { setApiKey(""); openerRef.current?.focus(); setOpen(false); };
  useLayoutEffect(() => {
    if (!open) return;
    const focusables = (): HTMLElement[] => [...(dialogRef.current?.querySelectorAll<HTMLElement>("button, input, select") ?? [])].filter((item) => !item.hasAttribute("disabled"));
    focusables()[0]?.focus();
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") { event.preventDefault(); close(); return; }
      if (event.key !== "Tab") return;
      const items = focusables();
      if (!items.length) return;
      const current = items.indexOf(document.activeElement as HTMLElement);
      if (event.shiftKey && current <= 0) { event.preventDefault(); items.at(-1)?.focus(); }
      if (!event.shiftKey && (current < 0 || current === items.length - 1)) { event.preventDefault(); items[0]?.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);
  const changeKind = (next: ProviderProfile["kind"]): void => { setKind(next); setModel(next === "deepseek" ? "deepseek-chat" : "qwen-plus"); };
  const submit = (event: FormEvent): void => {
    event.preventDefault();
    if (!api.createProvider || !api.setSessionCredential || !apiKey || disabled) return;
    void (async () => { try { const profile = await api.createProvider!(kind, model); const configured = await api.setSessionCredential!(profile.id, apiKey); onProvidersChange([...providers, configured]); onSelect(configured.id); close(); } catch { /* 凭据只保留在当前会话输入中，失败时不回显。 */ } finally { setApiKey(""); } })();
  };
  return <section className="provider-settings" aria-label="Provider 设置">
    <div className="provider-row"><strong>{selectedId ? "已选择 Provider Profile" : "确定性 Mock 演示"}</strong><button ref={openerRef} type="button" onClick={() => setOpen(true)} disabled={disabled}>高级设置</button></div>
    <label htmlFor="provider-profile">已配置 Profile</label>
    <select id="provider-profile" value={selectedId} onChange={(event) => onSelect(event.target.value)} disabled={disabled}><option value="">请选择（Mock）</option>{providers.filter((item) => item.configured).map((item) => <option key={item.id} value={item.id}>{item.kind}: {item.model}</option>)}</select>
    {open && <div className="provider-backdrop" role="presentation"><div className="provider-dialog" ref={dialogRef} role="dialog" aria-modal="true" aria-label="Provider 高级设置">
      <header><h2>Provider 高级设置</h2><button type="button" onClick={close}>关闭</button></header>
      <p>会话凭据不会持久保存。当前 WebUI 没有连接测试和主动清除；真实外网 Provider 任务尚未验收。</p>
      {!api.createProvider || !api.setSessionCredential ? <p>当前服务未开放 Provider 配置接口。</p> : <form onSubmit={submit}>
        <label htmlFor="provider-kind">类型</label><select id="provider-kind" value={kind} onChange={(event) => changeKind(event.target.value as ProviderProfile["kind"])}><option value="deepseek">deepseek</option><option value="qwen">qwen</option></select>
        <label htmlFor="provider-model">模型</label><input id="provider-model" value={model} onChange={(event) => setModel(event.target.value)} required />
        <label htmlFor="provider-key">API Key</label><input id="provider-key" type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} required />
        <button type="submit" disabled={disabled}>配置会话 Provider</button>
      </form>}
    </div></div>}
  </section>;
}

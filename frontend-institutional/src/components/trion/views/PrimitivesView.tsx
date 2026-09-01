"use client";

import {
  Binary,
  Dna,
  Fingerprint,
  FlaskConical,
  Flame,
  Scale,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useTrionPoll } from "@/lib/trion/hooks";
import { trionPost } from "@/lib/trion/client";
import { MeterBar, StatCounter } from "@/components/trion/viz/primitives";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

/* ── Local view-level types mirroring backend payloads ───────────────────── */

interface BhStats {
  total_tx_bhs: number;
  chains_with_data: number;
  payload_bytes: number;
  per_chain?: Record<string, number>;
  per_event_type?: Record<string, number>;
  formula?: string;
  whitepaper?: string;
}

interface HashDnaResponse {
  hash_dna: string;
  domain_separator: string;
  currency_id: string;
  magnitude_normalized: number;
  payload_fields: number;
  timestamp: number;
  whitepaper: string;
}

interface ExtendedBhResponse {
  bh: {
    sense_hex: string;
    antisense_hex: string;
    valid: boolean;
    payload_len: number;
    payload_version: string;
    domain_separator: string;
    event_type: string;
    event_type_id: number;
    magnitude_normalized: number;
    timestamp: number;
    block_number: number;
    chain_id: number;
    nonce: number;
    counterparty_id_hex: string;
    context_hash_hex: string;
  };
  domain_magic: string;
  payload_len: number;
  payload_version: string;
  whitepaper: string;
}

interface SelfFeed {
  feed: Array<{
    genomic_generation?: number;
    genomic_key?: string;
    archetype?: string;
    coherence_score?: number;
  }>;
}

/* ── Protocol constants (whitepaper L0 / L4 / L0.3 / L0.5) ───────────────── */

/** 93-byte canonical BH payload layout — L0.1 static reference. */
const BH_BYTE_LAYOUT: Array<{ field: string; bytes: number; color: string }> = [
  { field: "ENTITY_ID", bytes: 32, color: "#10b981" },
  { field: "VERSION", bytes: 1, color: "#f59e0b" },
  { field: "TIMESTAMP", bytes: 8, color: "#22d3ee" },
  { field: "MAGNITUDE", bytes: 8, color: "#a78bfa" },
  { field: "VALUE", bytes: 8, color: "#34d399" },
  { field: "EVENT_TYPE", bytes: 4, color: "#f43f5e" },
  { field: "CHAIN/EXTRA", bytes: 32, color: "#7d8896" },
];

/** Packed uint256 on-chain signal layout — 256 bits. */
const SIGNAL_BIT_LAYOUT: Array<{ field: string; bits: number; color: string }> = [
  { field: "STATUS", bits: 8, color: "#f59e0b" },
  { field: "C × 10⁶", bits: 32, color: "#10b981" },
  { field: "Θ × 10⁶", bits: 32, color: "#f43f5e" },
  { field: "BLOCK", bits: 64, color: "#22d3ee" },
  { field: "TIMESTAMP", bits: 64, color: "#a78bfa" },
  { field: "PLANE", bits: 56, color: "#34d399" },
];

/** 20 VM-agnostic event types with behavioral resonance weights (L0.3). */
const EVENT_WEIGHTS: Array<{ type: string; weight: number }> = [
  { type: "TRANSFER", weight: 1.0 },
  { type: "SWAP", weight: 1.1 },
  { type: "LIQUIDITY", weight: 1.3 },
  { type: "STAKE", weight: 1.2 },
  { type: "UNSTAKE", weight: 1.2 },
  { type: "GOVERNANCE", weight: 1.5 },
  { type: "PROPOSAL", weight: 1.7 },
  { type: "BORROW", weight: 1.4 },
  { type: "REPAY", weight: 1.4 },
  { type: "LIQUIDATE", weight: 1.6 },
  { type: "BRIDGE", weight: 1.1 },
  { type: "DEPLOY", weight: 2.0 },
  { type: "UPGRADE", weight: 2.0 },
  { type: "MINT", weight: 1.1 },
  { type: "BURN", weight: 1.1 },
  { type: "ORACLE_UPDATE", weight: 1.5 },
  { type: "MEV_CAPTURE", weight: 1.8 },
  { type: "FLASH_LOAN", weight: 1.8 },
  { type: "AIRDROP", weight: 1.2 },
  { type: "CLAIM", weight: 0.9 },
];

/** 8 living-security DNA components — protocol constants (Part 6 §6.2). */
const DNA_COMPONENTS: Array<{
  id: string;
  fn: string;
  name: string;
  detail: string;
  color: string;
}> = [
  { id: "G1", fn: "REPLICATION", name: "Genomic Key Evolution", detail: "GK(t) = Hash_DNA(GK(t−1) ‖ BE ‖ TM ‖ CV)", color: "#10b981" },
  { id: "G2", fn: "INTEGRITY", name: "Complementary Strand", detail: "XOR complement invariant — tamper-evident", color: "#22d3ee" },
  { id: "G3", fn: "ADAPTATION", name: "Immune System", detail: "innate + adaptive + memory responses", color: "#a78bfa" },
  { id: "G4", fn: "HOMEOSTASIS", name: "Epigenetic Layer", detail: "EL_state = f(threat, health, entropy)", color: "#34d399" },
  { id: "G5", fn: "DIVERSITY", name: "Genetic Recombination", detail: "periodic re-derivation from history", color: "#f59e0b" },
  { id: "G6", fn: "METABOLISM", name: "Cryptographic Noise", detail: "decoy sequences — noise is authentication", color: "#f43f5e" },
  { id: "G7", fn: "REPAIR", name: "Mitochondrial Core", detail: "independent protocol-integrity DNA", color: "#10b981" },
  { id: "G8", fn: "APOPTOSIS", name: "CRISPR Defense", detail: "surgical removal of compromised components", color: "#22d3ee" },
];

const EVENT_TYPE_NAMES = EVENT_WEIGHTS.map((e) => e.type);

const TOTAL_BH_BYTES = BH_BYTE_LAYOUT.reduce((s, f) => s + f.bytes, 0); // 93
const TOTAL_SIGNAL_BITS = SIGNAL_BIT_LAYOUT.reduce((s, f) => s + f.bits, 0); // 256

/** Attach running offsets to a static byte/bit layout (pure, module scope). */
function withOffsets<T extends { bytes?: number; bits?: number }>(
  layout: T[]
): Array<T & { offset: number }> {
  const out: Array<T & { offset: number }> = [];
  let off = 0;
  for (const f of layout) {
    out.push({ ...f, offset: off });
    off += f.bytes ?? f.bits ?? 0;
  }
  return out;
}

const BH_BYTE_SEGMENTS = withOffsets(BH_BYTE_LAYOUT);
const SIGNAL_BIT_SEGMENTS = withOffsets(SIGNAL_BIT_LAYOUT);

/* ── View ─────────────────────────────────────────────────────────────────── */

export function PrimitivesView() {
  const { data: bhStats } = useTrionPoll<BhStats>("bh/stats", 10000);
  const { data: selfFeed } = useTrionPoll<SelfFeed>("feed", 8000);

  const genomic = selfFeed?.feed?.[0];

  return (
    <div className="space-y-4">
      {/* ── A. Behavioral Hash anatomy (static reference card) ──────────── */}
      <section
        aria-label="Behavioral hash anatomy"
        className="trion-panel relative overflow-hidden p-5 sm:p-6"
      >
        <div
          className="pointer-events-none absolute -left-24 -top-24 h-64 w-64 rounded-full"
          style={{ background: "radial-gradient(circle, rgba(34,211,238,0.06) 0%, transparent 70%)" }}
          aria-hidden
        />
        <div className="flex flex-col gap-5 lg:flex-row lg:justify-between">
          <div className="min-w-0 max-w-2xl">
            <div className="flex items-center gap-2">
              <Dna size={14} className="text-[#10b981]" />
              <span className="trion-label">L0.1 · Behavioral Hash Anatomy · 93-Byte Canonical Payload</span>
            </div>
            <div className="mt-3">
              <ByteMap />
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-[#7d8896]">
              Every chain event collapses into one dimensionless 93-byte payload.
              Oracle wire order: entity_id(32) ‖ event_type(1) ‖ magnitude(8) ‖
              context(8) ‖ timestamp(8) ‖ chain_id(4) ‖ block_hash(32).
            </p>
          </div>
          <div className="min-w-0 lg:max-w-md">
            <div className="rounded-lg border border-[#1c232d] bg-[#0a0d12] p-4">
              <div className="trion-label">Dual-Strand Construction</div>
              <div className="trion-mono mt-2 space-y-1.5 text-[12px] leading-relaxed">
                <div className="text-[#34d399]">sense = SHA3-256(93-byte ‖ 0x00)</div>
                <div className="text-[#22d3ee]">
                  antisense = SHA3-256(93-byte ‖ 0xFF) ⊕ NOT(sense)
                </div>
                <div className="text-[#4b5563] text-[10px]">
                  invariant: sense ⊕ antisense == NOT(SHA3-256(93-byte ‖ 0xFF))
                </div>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-[#1c232d] pt-3">
                <span className="trion-mono text-[10px] text-[#4b5563]">
                  {bhStats?.payload_bytes ?? 93}-byte payload
                </span>
                <span className="trion-mono text-[10px] text-[#4b5563]">
                  <StatCounter value={bhStats?.total_tx_bhs ?? 0} /> tx BHs hashed
                </span>
                <span className="trion-mono text-[10px] text-[#4b5563]">
                  tamper detection &lt; 2⁻¹²⁸ collision
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── B. Interactive hashers (HashDNA + extended v2 BH) ───────────── */}
      <HashLab />

      {/* ── C + D: magnitude normalization + genomic key ─────────────────── */}
      <section className="grid gap-4 lg:grid-cols-2">
        <MagnitudeLab />
        <GenomicKeyCard generation={genomic?.genomic_generation ?? 0} genomicKey={genomic?.genomic_key} />
      </section>

      {/* ── E + F: thermodynamic deletion + resonance / signal packing ──── */}
      <section className="grid gap-4 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <ThermodynamicCard />
        </div>
        <div className="lg:col-span-3">
          <ResonancePackingCard />
        </div>
      </section>
    </div>
  );
}

/* ── A. Byte-map (proportional memory-map of the 93-byte payload) ────────── */

function ByteMap() {
  return (
    <div>
      <div
        className="flex h-8 w-full overflow-hidden rounded-md border border-[#1c232d]"
        role="img"
        aria-label="93-byte behavioral hash payload byte map"
      >
        {BH_BYTE_SEGMENTS.map((s) => (
          <div
            key={s.field}
            className="flex h-full items-center justify-center overflow-hidden border-r border-[#0d1117] last:border-r-0 transition-colors"
            style={{ width: `${(s.bytes / TOTAL_BH_BYTES) * 100}%`, background: `${s.color}26` }}
            title={`${s.field} — ${s.bytes}B @ offset ${s.offset}`}
          >
            {s.bytes >= 8 && (
              <span className="trion-mono truncate px-1 text-[9px] font-semibold" style={{ color: s.color }}>
                {s.field}
              </span>
            )}
            {s.bytes < 8 && (
              <span className="trion-mono text-[9px] font-bold" style={{ color: s.color }}>
                {s.field.slice(0, 1)}
              </span>
            )}
          </div>
        ))}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
        {BH_BYTE_SEGMENTS.map((s) => (
          <div key={s.field} className="flex items-center gap-1.5 min-w-0">
            <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: s.color }} aria-hidden />
            <span className="trion-mono truncate text-[9px] text-[#7d8896]">
              {s.field} <span className="text-[#4b5563]">{s.bytes}B @{s.offset}</span>
            </span>
          </div>
        ))}
        <div className="col-span-2 flex items-center gap-1.5 sm:col-span-4">
          <span className="trion-mono text-[9px] text-[#4b5563]">
            total {TOTAL_BH_BYTES} bytes — big-endian, VM-agnostic
          </span>
        </div>
      </div>
    </div>
  );
}

/* ── B. Interactive hasher lab (HashDNA 420B keccak + extended v2 176B) ──── */

function HashLab() {
  const [tab, setTab] = useState<"dna" | "v2">("dna");

  return (
    <section aria-label="Interactive hash computation lab" className="trion-panel">
      <div className="flex flex-wrap items-center gap-3 border-b border-[#1c232d] px-5 py-3">
        <FlaskConical size={13} className="text-[#22d3ee]" />
        <span className="trion-label">Primitive Hash Lab · Live Oracle Computation</span>
        <div className="ml-auto flex gap-1.5">
          <button
            onClick={() => setTab("dna")}
            aria-pressed={tab === "dna"}
            className={`trion-mono rounded border px-2.5 py-1 text-[10px] font-semibold transition-colors ${
              tab === "dna"
                ? "border-[#10b98166] bg-[#10b98112] text-[#34d399]"
                : "border-[#1c232d] bg-[#0d1117] text-[#7d8896] hover:border-[#2a3441] hover:text-[#d7dde6]"
            }`}
          >
            HASHDNA · 420B KECCAK
          </button>
          <button
            onClick={() => setTab("v2")}
            aria-pressed={tab === "v2"}
            className={`trion-mono rounded border px-2.5 py-1 text-[10px] font-semibold transition-colors ${
              tab === "v2"
                ? "border-[#22d3ee66] bg-[#22d3ee12] text-[#22d3ee]"
                : "border-[#1c232d] bg-[#0d1117] text-[#7d8896] hover:border-[#2a3441] hover:text-[#d7dde6]"
            }`}
          >
            EXTENDED BH · 176B V2
          </button>
        </div>
      </div>
      <div className="p-5">{tab === "dna" ? <HashDnaForm /> : <ExtendedBhForm />}</div>
    </section>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  wide = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  wide?: boolean;
}) {
  return (
    <label className={`block min-w-0 ${wide ? "sm:col-span-2" : ""}`}>
      <span className="trion-label">{label}</span>
      <Input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="trion-mono mt-1 h-8 rounded border-[#1c232d] bg-[#0a0d12] px-2.5 text-[11px] text-[#d7dde6] placeholder:text-[#4b5563] focus-visible:border-[#10b981] focus-visible:ring-0 focus-visible:ring-offset-0"
        aria-label={label}
      />
    </label>
  );
}

function ResultError({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div className="rounded-md border border-[#f43f5e44] bg-[#f43f5e0f] p-3">
      <span className="trion-mono text-[11px] text-[#f43f5e]">{error}</span>
    </div>
  );
}

function HashDnaForm() {
  const [form, setForm] = useState({
    entity_id_hex: "deadbeef".repeat(8),
    event_type_id: "1",
    raw_amount: "1000000",
    asset_decimals: "6",
    asset_symbol: "USDC",
    asset_chain_id: "1",
    chain_id: "1",
    block_number: "18000000",
    nonce: "7",
    counterparty_id_hex: "",
    protocol_id_hex: "",
  });
  const [result, setResult] = useState<HashDnaResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const body = useMemo(
    () => ({
      entity_id_hex: form.entity_id_hex.trim() || "01".repeat(32),
      event_type_id: parseInt(form.event_type_id, 10) || 1,
      raw_amount: parseInt(form.raw_amount, 10) || 10 ** 18,
      asset_decimals: parseInt(form.asset_decimals, 10) || 18,
      asset_symbol: form.asset_symbol.trim() || "USDC",
      asset_chain_id: parseInt(form.asset_chain_id, 10) || 1,
      asset_address: "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
      chain_id: parseInt(form.chain_id, 10) || 1,
      block_number: parseInt(form.block_number, 10) || 18000000,
      block_hash_hex: "cc".repeat(32),
      contract_address: "0x1d129D34279d1246aB08a41dfE610EaF8D794237",
      counterparty_id_hex: form.counterparty_id_hex.trim() || undefined,
      protocol_id_hex: form.protocol_id_hex.trim() || undefined,
      btcp_version: 1,
      nonce: parseInt(form.nonce, 10) || 0,
    }),
    [form]
  );

  const submit = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await trionPost<HashDnaResponse>("btcp/hash_dna", body);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "POST failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div>
        <p className="text-[11px] leading-relaxed text-[#7d8896]">
          Hash_DNA(event) = keccak-256 over the 420-byte payload (14 fields,
          13×32B + 4B version). Domain separation:
          <span className="trion-mono text-[#34d399]"> TRION_BEHAVIORAL_HASH_V1</span> ‖ chain_id ‖ contract.
        </p>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Entity ID (hex32)" value={form.entity_id_hex} onChange={set("entity_id_hex")} placeholder="64 hex chars" wide />
          <Field label="Event Type ID (1–20)" value={form.event_type_id} onChange={set("event_type_id")} type="number" />
          <Field label="Chain ID" value={form.chain_id} onChange={set("chain_id")} type="number" />
          <Field label="Raw Amount" value={form.raw_amount} onChange={set("raw_amount")} type="number" />
          <Field label="Asset Decimals" value={form.asset_decimals} onChange={set("asset_decimals")} type="number" />
          <Field label="Asset Symbol" value={form.asset_symbol} onChange={set("asset_symbol")} />
          <Field label="Asset Chain ID" value={form.asset_chain_id} onChange={set("asset_chain_id")} type="number" />
          <Field label="Block Number" value={form.block_number} onChange={set("block_number")} type="number" />
          <Field label="Nonce (replay guard)" value={form.nonce} onChange={set("nonce")} type="number" />
          <Field label="Counterparty (hex, opt)" value={form.counterparty_id_hex} onChange={set("counterparty_id_hex")} placeholder="64 hex chars" />
        </div>
        <div className="mt-4">
          <Button
            onClick={submit}
            disabled={loading}
            variant="outline"
            className="h-9 rounded border-[#10b98144] bg-[#10b98112] px-4 text-[11px] font-semibold text-[#34d399] hover:bg-[#10b9811f] hover:text-[#6ee7b7] disabled:opacity-50"
          >
            {loading ? "COMPUTING…" : "COMPUTE HASH_DNA"}
          </Button>
        </div>
        <div className="mt-4">
          <div className="trion-label">Request JSON (POST /api/v1/btcp/hash_dna)</div>
          <pre className="trion-mono mt-1.5 max-h-48 overflow-auto rounded-md border border-[#1c232d] bg-[#0a0d12] p-3 text-[10px] leading-relaxed text-[#7d8896]">
            {JSON.stringify(body, null, 2)}
          </pre>
        </div>
      </div>
      <div className="min-w-0">
        <div className="trion-label">Oracle Response</div>
        {loading && (
          <div className="trion-mono mt-2 text-[11px] text-[#4b5563]">
            posting payload to sensing oracle…
          </div>
        )}
        <ResultError error={error} />
        {result && (
          <div className="mt-2 space-y-3">
            <div className="rounded-md border border-[#10b98144] bg-[#10b9810a] p-4">
              <div className="trion-label">Hash_DNA · keccak-256(420B)</div>
              <div className="trion-mono mt-1.5 break-all text-[13px] font-bold leading-relaxed text-[#34d399]">
                {result.hash_dna}
              </div>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <KV label="Domain Separator" value={`0x${result.domain_separator.slice(0, 32)}…`} full />
              <KV label="Currency ID (asset)" value={`0x${result.currency_id.slice(0, 32)}…`} full />
              <KV label="Magnitude (18-dec)" value={result.magnitude_normalized.toLocaleString()} />
              <KV label="Payload Fields" value={String(result.payload_fields)} />
            </div>
            <div className="trion-mono text-[10px] text-[#4b5563]">
              {result.whitepaper} · oracle ts {result.timestamp}
            </div>
          </div>
        )}
        {!loading && !error && !result && (
          <div className="mt-2 rounded-md border border-dashed border-[#1c232d] p-4 text-[11px] text-[#7d8896]">
            Defaults are pre-filled — press COMPUTE to hash a live event.
          </div>
        )}
      </div>
    </div>
  );
}

function ExtendedBhForm() {
  const [form, setForm] = useState({
    entity_id_hex: "deadbeef".repeat(8),
    event_type: "TRANSFER",
    magnitude_raw: "4200000",
    magnitude_max_90d: "900000000",
    chain_id: "137",
    block_number: "65000000",
    nonce: "",
    timestamp: String(Math.floor(Date.now() / 1000)),
  });
  const [result, setResult] = useState<ExtendedBhResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const body = useMemo(() => {
    const b: Record<string, unknown> = {
      entity_id_hex: form.entity_id_hex.trim(),
      event_type: form.event_type,
      magnitude_raw: parseInt(form.magnitude_raw, 10) || 0,
      magnitude_decimals: 6,
      magnitude_max_90d: parseInt(form.magnitude_max_90d, 10) || 10 ** 18,
      magnitude_currency_id: 0,
      timestamp: parseInt(form.timestamp, 10) || 0,
      block_number: parseInt(form.block_number, 10) || 0,
      block_hash_hex: "ab".repeat(32),
      chain_id: parseInt(form.chain_id, 10) || 1,
      counterparty_id_hex: "cd".repeat(32),
      protocol_id: 2,
      context_hex: "0011223344556677",
      btcp_version: 1,
    };
    const n = parseInt(form.nonce, 10);
    if (!Number.isNaN(n) && form.nonce.trim() !== "") b.nonce = n;
    return b;
  }, [form]);

  const submit = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await trionPost<ExtendedBhResponse>("bh/v2/extended", body);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "POST failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div>
        <p className="text-[11px] leading-relaxed text-[#7d8896]">
          Extended v2 BH — 176-byte payload with replay protection and cross-chain
          domain separation (<span className="trion-mono text-[#22d3ee]">DOMAIN_MAGIC 0x54524f4e</span>).
          Leave nonce empty to let the oracle draw a CSPRNG nonce.
        </p>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Entity ID (hex32)" value={form.entity_id_hex} onChange={set("entity_id_hex")} placeholder="64 hex chars" wide />
          <label className="block min-w-0">
            <span className="trion-label">Event Type</span>
            <select
              value={form.event_type}
              onChange={(e) => set("event_type")(e.target.value)}
              className="trion-mono mt-1 h-8 w-full rounded border border-[#1c232d] bg-[#0a0d12] px-2 text-[11px] text-[#d7dde6] focus:border-[#22d3ee]"
              aria-label="Event type"
            >
              {EVENT_TYPE_NAMES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
          <Field label="Magnitude Raw" value={form.magnitude_raw} onChange={set("magnitude_raw")} type="number" />
          <Field label="Magnitude Max 90d" value={form.magnitude_max_90d} onChange={set("magnitude_max_90d")} type="number" />
          <Field label="Chain ID" value={form.chain_id} onChange={set("chain_id")} type="number" />
          <Field label="Block Number" value={form.block_number} onChange={set("block_number")} type="number" />
          <Field label="Timestamp (unix)" value={form.timestamp} onChange={set("timestamp")} type="number" />
          <Field label="Nonce (empty = CSPRNG)" value={form.nonce} onChange={set("nonce")} type="number" placeholder="auto" />
        </div>
        <div className="mt-4">
          <Button
            onClick={submit}
            disabled={loading}
            variant="outline"
            className="h-9 rounded border-[#22d3ee44] bg-[#22d3ee12] px-4 text-[11px] font-semibold text-[#22d3ee] hover:bg-[#22d3ee1f] hover:text-[#67e8f9] disabled:opacity-50"
          >
            {loading ? "COMPUTING…" : "COMPUTE EXTENDED BH"}
          </Button>
        </div>
        <div className="mt-4">
          <div className="trion-label">Request JSON (POST /api/v1/bh/v2/extended)</div>
          <pre className="trion-mono mt-1.5 max-h-48 overflow-auto rounded-md border border-[#1c232d] bg-[#0a0d12] p-3 text-[10px] leading-relaxed text-[#7d8896]">
            {JSON.stringify(body, null, 2)}
          </pre>
        </div>
      </div>
      <div className="min-w-0">
        <div className="trion-label">Oracle Response</div>
        {loading && (
          <div className="trion-mono mt-2 text-[11px] text-[#4b5563]">
            posting payload to sensing oracle…
          </div>
        )}
        <ResultError error={error} />
        {result && (
          <div className="mt-2 space-y-3">
            <div className="grid grid-cols-1 gap-2">
              <div className="rounded-md border border-[#10b98144] bg-[#10b9810a] p-3">
                <div className="trion-label">Sense Strand · SHA3-256(176B ‖ 0x00)</div>
                <div className="trion-mono mt-1 break-all text-[11px] leading-relaxed text-[#34d399]">
                  {result.bh.sense_hex}
                </div>
              </div>
              <div className="rounded-md border border-[#22d3ee44] bg-[#22d3ee0a] p-3">
                <div className="trion-label">Antisense Strand · ⊕ NOT(sense)</div>
                <div className="trion-mono mt-1 break-all text-[11px] leading-relaxed text-[#22d3ee]">
                  {result.bh.antisense_hex}
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <KV label="Payload" value={`${result.payload_len} B · ${result.payload_version}`} />
              <KV label="Domain Magic" value={`0x${result.domain_magic}`} />
              <KV label="Event" value={`${result.bh.event_type} (#${result.bh.event_type_id})`} />
              <KV label="Magnitude Norm" value={result.bh.magnitude_normalized.toFixed(6)} />
              <KV label="Chain" value={String(result.bh.chain_id)} />
              <KV label="Nonce" value={String(result.bh.nonce)} />
            </div>
            <div className="trion-mono text-[10px] text-[#4b5563]">{result.whitepaper}</div>
          </div>
        )}
        {!loading && !error && !result && (
          <div className="mt-2 rounded-md border border-dashed border-[#1c232d] p-4 text-[11px] text-[#7d8896]">
            Defaults are pre-filled — press COMPUTE to hash a live event.
          </div>
        )}
      </div>
    </div>
  );
}

function KV({ label, value, full = false }: { label: string; value: string; full?: boolean }) {
  return (
    <div className={`rounded-md border border-[#1c232d] bg-[#0a0d12] p-2.5 ${full ? "sm:col-span-2" : ""}`}>
      <div className="trion-label">{label}</div>
      <div className="trion-mono mt-0.5 break-all text-[10px] text-[#d7dde6]">{value}</div>
    </div>
  );
}

/* ── C. Magnitude normalization lab ───────────────────────────────────────── */

function MagnitudeLab() {
  const [value, setValue] = useState("4.2");
  const [max, setMax] = useState("900");

  const v = Number(value) || 0;
  const m = Number(max) || 0;
  const denom = Math.log10(m + 1);
  const norm = denom > 0 ? Math.log10(v + 1) / denom : 0;
  const nano = Math.round(norm * 1e9);

  return (
    <div className="trion-panel p-5">
      <div className="flex items-center gap-2">
        <Scale size={13} className="text-[#a78bfa]" />
        <span className="trion-label">L0.1 §3.2 · Magnitude Normalization</span>
      </div>
      <div className="trion-mono mt-2 rounded-md border border-[#1c232d] bg-[#0a0d12] p-3 text-[11px] text-[#a78bfa]">
        M_norm = log10(v+1) / log10(max_90d+1) · ×10⁹ nano scaling
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-[#7d8896]">
        Raw amounts are squashed to [0,1] against the entity 90-day maximum so a
        42,000,000-wei transfer and a 900-token transfer compare dimensionlessly
        across chains and assets.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <Field label="Value v (human units)" value={value} onChange={setValue} type="number" />
        <Field label="max_90d (window max)" value={max} onChange={setMax} type="number" />
      </div>
      <div className="mt-4 rounded-md border border-[#1c232d] bg-[#0a0d12] p-3">
        <div className="trion-mono space-y-1 text-[11px] text-[#7d8896]">
          <div>log10(v+1) = <span className="text-[#d7dde6]">{Math.log10(v + 1).toFixed(6)}</span></div>
          <div>log10(max+1) = <span className="text-[#d7dde6]">{denom.toFixed(6)}</span></div>
          <div className="text-[#a78bfa]">
            M_norm = <span className="font-bold">{norm.toFixed(6)}</span>
          </div>
          <div>
            nano = M_norm × 10⁹ = <span className="text-[#34d399]">{nano.toLocaleString()}</span>
          </div>
        </div>
        <div className="mt-3">
          <MeterBar label="M_norm ∈ [0,1]" value={norm} color="#a78bfa" />
        </div>
      </div>
      <div className="mt-3 trion-mono text-[10px] text-[#4b5563]">
        8-byte magnitude field carries nano-units (uint64) in the canonical payload.
      </div>
    </div>
  );
}

/* ── D. Genomic Key card ──────────────────────────────────────────────────── */

function GenomicKeyCard({
  generation,
  genomicKey,
}: {
  generation: number;
  genomicKey?: string;
}) {
  return (
    <div className="trion-panel p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Fingerprint size={13} className="text-[#10b981]" />
          <span className="trion-label">L4.3–4.6 · Genomic Key · Living Security DNA</span>
        </div>
        <span className="trion-mono text-[10px] text-[#4b5563]">8 components · protocol constants</span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-3">
          <div className="trion-label">Dual-Strand Signature · 64B</div>
          <div className="mt-2 flex gap-1">
            <div className="flex h-6 flex-1 items-center justify-center rounded-l border border-[#10b98144] bg-[#10b98112]">
              <span className="trion-mono text-[9px] font-bold text-[#34d399]">SENSE 32B</span>
            </div>
            <div className="flex h-6 flex-1 items-center justify-center rounded-r border border-[#22d3ee44] bg-[#22d3ee12]">
              <span className="trion-mono text-[9px] font-bold text-[#22d3ee]">ANTISENSE 32B</span>
            </div>
          </div>
          <div className="trion-mono mt-1.5 break-all text-[9px] leading-relaxed text-[#4b5563]">
            {genomicKey
              ? `${genomicKey.slice(0, 32)} ‖ ${genomicKey.slice(32, 64)}`
              : "hash_dna_64: sense ‖ antisense — complement-verified"}
          </div>
        </div>
        <div className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-3">
          <div className="trion-label">Generation Counter (live)</div>
          <div className="trion-mono mt-1 text-2xl font-bold tabular-nums text-[#34d399]">
            <StatCounter value={generation} />
          </div>
          <div className="trion-mono mt-1.5 text-[9px] leading-relaxed text-[#4b5563]">
            Key_gen_N = H(Key_gen_N−1 ‖ trigger ‖ block_hash ‖ sig)
          </div>
        </div>
      </div>

      <div className="mt-3 space-y-1.5">
        {DNA_COMPONENTS.map((c) => (
          <div
            key={c.id}
            className="flex items-center gap-3 rounded-md border border-[#161b22] bg-[#0a0d12] px-3 py-2 transition-colors hover:border-[#2a3441]"
          >
            <span className="trion-mono w-7 shrink-0 text-[10px] font-bold" style={{ color: c.color }}>
              {c.id}
            </span>
            <span
              className="trion-mono hidden w-[110px] shrink-0 text-[9px] font-semibold tracking-wider sm:inline"
              style={{ color: c.color }}
            >
              {c.fn}
            </span>
            <div className="min-w-0">
              <div className="text-[11px] font-medium text-[#d7dde6]">{c.name}</div>
              <div className="trion-mono truncate text-[10px] text-[#7d8896]">{c.detail}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="trion-mono mt-3 border-t border-[#1c232d] pt-2.5 text-[10px] text-[#4b5563]">
        SEC(t) = LSS(t) · PQC(t) · CC(t) · rotation: 365 epochs · recombination: 30 epochs
      </div>
    </div>
  );
}

/* ── E. Thermodynamic deletion card ───────────────────────────────────────── */

function ThermodynamicCard() {
  const [iGain, setIGain] = useState("1.6");
  const [sCost, setSCost] = useState("1.2");
  const ig = Number(iGain) || 0;
  const sc = Number(sCost) || 0;
  const ratio = sc > 0 ? ig / sc : 0;
  const selected = ratio > 1.0;

  return (
    <div className="trion-panel p-5">
      <div className="flex items-center gap-2">
        <Flame size={13} className="text-[#f43f5e]" />
        <span className="trion-label">L9.2 · Thermodynamic Deletion · Entropy Engine</span>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-[#7d8896]">
        Deletion is made physically costly: removing a record from the Akashic
        index must increase total system entropy (ΔS &gt; 0), so the ledger
        refuses silent drops and charges the full entropy bill instead.
        Haskell T8 types the ledger append-only — deletion is unrepresentable.
      </p>
      <div className="mt-3 space-y-2">
        <div className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-3">
          <div className="trion-label">Information Conservation Ledger</div>
          <div className="trion-mono mt-1.5 text-[11px] leading-relaxed text-[#34d399]">
            I_TRION(t) = BH_generated + A_absorbed − S_emitted − E_lost
          </div>
          <div className="trion-mono mt-1 text-[10px] text-[#4b5563]">
            I_total(t) = I_total(t−1) + ΔI_consumed − ΔI_transformed
          </div>
        </div>
        <div className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-3">
          <div className="flex items-center justify-between">
            <span className="trion-label">Signal Selection · KL Information Gain</span>
            <span className="trion-mono text-[10px] text-[#f59e0b]">θ = 1.0</span>
          </div>
          <div className="trion-mono mt-1.5 text-[11px] text-[#f59e0b]">
            selected ⟺ dI_gained / dS_entropy_cost &gt; θ_selection
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <Field label="ΔI gained (nats)" value={iGain} onChange={setIGain} type="number" />
            <Field label="ΔS entropy cost" value={sCost} onChange={setSCost} type="number" />
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className="trion-mono text-[11px] text-[#7d8896]">
              ratio = <span className="font-bold text-[#d7dde6]">{ratio.toFixed(4)}</span>
            </span>
            <span
              className={`trion-mono rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase ${
                selected
                  ? "border-[#10b98144] bg-[#10b98112] text-[#34d399]"
                  : "border-[#f43f5e44] bg-[#f43f5e12] text-[#f43f5e]"
              }`}
            >
              {selected ? "signal selected" : "signal rejected"}
            </span>
          </div>
          <div className="mt-2">
            <MeterBar label="dI / dS vs θ" value={Math.min(1, ratio / 2)} threshold={0.5} color="#f59e0b" />
          </div>
        </div>
      </div>
      <div className="trion-mono mt-3 text-[10px] text-[#4b5563]">
        conservation tolerance 1e-6 · floor at I=0 · every BH emitted is auditable
      </div>
    </div>
  );
}

/* ── F. Resonance weights + uint256 signal packing ────────────────────────── */

function ResonancePackingCard() {
  const top6 = [...EVENT_WEIGHTS].sort((a, b) => b.weight - a.weight).slice(0, 6);
  const rest = [...EVENT_WEIGHTS].sort((a, b) => b.weight - a.weight).slice(6);

  return (
    <div className="trion-panel p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Binary size={13} className="text-[#22d3ee]" />
          <span className="trion-label">L0.3 / L5 · Resonance Weights &amp; Signal Packing</span>
        </div>
        <span className="trion-mono text-[10px] text-[#4b5563]">20 event types · 1 uint256</span>
      </div>

      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        {/* Event resonance weights */}
        <div>
          <div className="trion-label">Event Resonance Weights (top 6 of 20)</div>
          <div className="mt-2 space-y-1.5">
            {top6.map((e) => (
              <div key={e.type} className="flex items-center gap-2.5">
                <span className="trion-mono w-[110px] shrink-0 truncate text-[10px] text-[#d7dde6]">
                  {e.type}
                </span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[#1c232d]">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{ width: `${(e.weight / 2.0) * 100}%`, background: "#10b981" }}
                  />
                </div>
                <span className="trion-mono w-9 shrink-0 text-right text-[10px] tabular-nums text-[#34d399]">
                  {e.weight.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {rest.map((e) => (
              <span
                key={e.type}
                className="trion-mono rounded border border-[#161b22] bg-[#0a0d12] px-1.5 py-0.5 text-[9px] text-[#7d8896]"
                title={`weight ${e.weight.toFixed(2)}`}
              >
                {e.type} <span className="text-[#4b5563]">{e.weight.toFixed(2)}</span>
              </span>
            ))}
          </div>
          <div className="trion-mono mt-2.5 text-[10px] text-[#4b5563]">
            weights 0.90–2.00 · Comm(A,B) ⟺ ∃f : RF(A,f) &gt; 0 ∧ RF(B,f) &gt; 0
          </div>
        </div>

        {/* uint256 bit-field map */}
        <div>
          <div className="trion-label">Packed uint256 Signal · Bit-Field Map (256 bits)</div>
          <div
            className="mt-2 flex h-8 w-full overflow-hidden rounded-md border border-[#1c232d]"
            role="img"
            aria-label="256-bit packed signal layout"
          >
            {SIGNAL_BIT_SEGMENTS.map((s) => (
              <div
                key={s.field}
                className="flex h-full items-center justify-center overflow-hidden border-r border-[#0d1117] last:border-r-0"
                style={{ width: `${(s.bits / TOTAL_SIGNAL_BITS) * 100}%`, background: `${s.color}26` }}
                title={`${s.field} — ${s.bits} bits @ bit ${s.offset}`}
              >
                {s.bits >= 32 && (
                  <span className="trion-mono truncate px-1 text-[9px] font-semibold" style={{ color: s.color }}>
                    {s.field}
                  </span>
                )}
                {s.bits < 32 && (
                  <span className="trion-mono text-[9px] font-bold" style={{ color: s.color }}>
                    {s.field.slice(0, 3)}
                  </span>
                )}
              </div>
            ))}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1">
            {SIGNAL_BIT_SEGMENTS.map((s) => (
              <div key={s.field} className="flex items-center gap-1.5 min-w-0">
                <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: s.color }} aria-hidden />
                <span className="trion-mono truncate text-[9px] text-[#7d8896]">
                  {s.field} <span className="text-[#4b5563]">{s.bits}b @{s.offset}</span>
                </span>
              </div>
            ))}
          </div>
          <div className="trion-mono mt-2.5 rounded-md border border-[#1c232d] bg-[#0a0d12] p-2.5 text-[10px] leading-relaxed text-[#4b5563]">
            shift layout: status&lt;&lt;0 · C×10⁶&lt;&lt;8 · Θ×10⁶&lt;&lt;40 · block&lt;&lt;72 ·
            ts&lt;&lt;136 · plane&lt;&lt;200 — one 32-byte word per entity per epoch,
            published to the on-chain oracle.
          </div>
        </div>
      </div>
    </div>
  );
}

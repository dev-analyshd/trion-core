/**
 * TRION Conscious Layer — Annotation Interface (TypeScript)
 *
 * Whitepaper Part 11 specifies TypeScript for "annotation interface, consuming
 * protocol libraries." This module provides the annotation interface for the
 * Conscious Plane (K) — where human wisdom annotates behavioral data.
 *
 * The annotation interface supports:
 * - 20+ languages (per L8 build level requirement)
 * - Stake-and-challenge mechanism (validators stake TRION to annotate)
 * - Indigenous Knowledge Interface (verified-consent registry)
 * - Elder Wisdom Protocol (tenure-based elevated weight)
 *
 * This is a client-side SDK module that connects to the Python anima-service
 * annotation APIs. It does NOT run the annotation logic itself — it provides
 * the type-safe interface for annotation submission, retrieval, and dispute.
 */

// ── Types ───────────────────────────────────────────────────────────────────

/**
 * Annotation types matching the whitepaper's Conscious Plane taxonomy.
 */
export enum AnnotationType {
  CULTURAL_CONTEXT = "CULTURAL_CONTEXT",
  EXPERT_JUDGMENT = "EXPERT_JUDGMENT",
  INDIGENOUS_KNOWLEDGE = "INDIGENOUS_KNOWLEDGE",
  ELDER_WISDOM = "ELDER_WISDOM",
  REGULATORY_CONTEXT = "REGULATORY_CONTEXT",
  BEHAVIORAL_ASSESSMENT = "BEHAVIORAL_ASSESSMENT",
}

/**
 * Supported annotation languages (L8 requirement: 20+ languages).
 */
export const SUPPORTED_LANGUAGES = [
  "en", "zh", "es", "hi", "ar", "pt", "ru", "ja", "de", "fr",
  "ko", "tr", "it", "id", "nl", "pl", "vi", "th", "fa", "he",
  "sw", "am", "yo", "ha",
] as const;

export type AnnotationLanguage = typeof SUPPORTED_LANGUAGES[number];

/**
 * An annotation submitted by a human annotator.
 */
export interface TRIONAnnotation {
  annotation_id: string;
  entity_id: string;
  annotation_type: AnnotationType;
  language: AnnotationLanguage;
  content: string;
  confidence: number; // [0, 1] — annotator's self-assessed confidence
  stake_amount?: bigint; // TRION tokens staked (stake-and-challenge)
  annotator_id: string;
  annotator_credentials: AnnotatorCredentials;
  cultural_context?: Record<string, unknown>;
  consent_verified: boolean; // required for INDIGENOUS_KNOWLEDGE
  timestamp: number;
  ttl: number; // seconds until expiry
}

/**
 * Annotator credentials — determines annotation weight.
 */
export interface AnnotatorCredentials {
  annotator_type: "EXPERT" | "INDIGENOUS_ELDER" | "COMMUNITY" | "REGULATOR";
  tenure_days: number; // for Elder Wisdom Protocol — 12+ months required
  accuracy_history: number; // rolling 90-day accuracy [0, 1]
  jurisdictions: string[];
  languages: AnnotationLanguage[];
  indigenous_consent_id?: string; // verified consent record ID
  stake_weight_multiplier: number; // ELDER=2.5, EXPERT=1.5, COMMUNITY=1.0
}

/**
 * Challenge to an existing annotation (stake-and-challenge mechanism).
 */
export interface AnnotationChallenge {
  challenge_id: string;
  annotation_id: string;
  challenger_id: string;
  challenge_bond: bigint; // TRION tokens staked to dispute
  reason: string;
  evidence: string[];
  timestamp: number;
  status: "PENDING" | "UPHELD" | "REJECTED" | "EXPIRED";
}

/**
 * Result of an annotation submission.
 */
export interface AnnotationResult {
  success: boolean;
  annotation_id: string;
  k_contribution: number; // contribution to K(t) plane
  stake_recorded: bigint;
  consensus_weight: number;
  error?: string;
}

// ── Annotation Interface Client ─────────────────────────────────────────────

export class AnnotationInterface {
  private baseUrl: string;
  private apiKey?: string;

  constructor(baseUrl: string, apiKey?: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.apiKey = apiKey;
  }

  private async request(path: string, options: RequestInit = {}): Promise<Response> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((options.headers as Record<string, string>) || {}),
    };
    if (this.apiKey) headers["X-API-Key"] = this.apiKey;
    return fetch(`${this.baseUrl}${path}`, { ...options, headers });
  }

  /**
   * Submit an annotation for an entity.
   * Whitepaper L8: "Annotation interface 20+ languages"
   */
  async submitAnnotation(annotation: Omit<TRIONAnnotation, "annotation_id" | "timestamp" | "ttl">): Promise<AnnotationResult> {
    const response = await this.request("/api/v1/annotations/submit", {
      method: "POST",
      body: JSON.stringify(annotation),
    });
    if (!response.ok) {
      return { success: false, annotation_id: "", k_contribution: 0, stake_recorded: 0n, consensus_weight: 0, error: `HTTP ${response.status}` };
    }
    return response.json();
  }

  /**
   * Retrieve annotations for an entity.
   */
  async getAnnotations(entityId: string, opts?: {
    type?: AnnotationType;
    language?: AnnotationLanguage;
    limit?: number;
  }): Promise<TRIONAnnotation[]> {
    const params = new URLSearchParams();
    if (opts?.type) params.set("type", opts.type);
    if (opts?.language) params.set("language", opts.language);
    if (opts?.limit) params.set("limit", String(opts.limit));
    const response = await this.request(`/api/v1/annotations/${entityId}?${params}`);
    if (!response.ok) return [];
    const data = await response.json();
    return data.annotations || [];
  }

  /**
   * Challenge an annotation (stake-and-challenge mechanism).
   * Whitepaper L8: "stake-and-challenge mechanism"
   */
  async challengeAnnotation(challenge: Omit<AnnotationChallenge, "challenge_id" | "timestamp" | "status">): Promise<{ success: boolean; challenge_id: string; error?: string }> {
    const response = await this.request("/api/v1/annotations/challenge", {
      method: "POST",
      body: JSON.stringify(challenge),
    });
    if (!response.ok) {
      return { success: false, challenge_id: "", error: `HTTP ${response.status}` };
    }
    return response.json();
  }

  /**
   * Register as an annotator.
   */
  async registerAnnotator(credentials: AnnotatorCredentials): Promise<{ success: boolean; annotator_id: string; error?: string }> {
    const response = await this.request("/api/v1/annotations/register", {
      method: "POST",
      body: JSON.stringify(credentials),
    });
    if (!response.ok) {
      return { success: false, annotator_id: "", error: `HTTP ${response.status}` };
    }
    return response.json();
  }

  /**
   * Submit indigenous knowledge with verified consent.
   * Whitepaper: "Indigenous Knowledge Interface built with those communities"
   */
  async submitIndigenousKnowledge(params: {
    entity_id: string;
    content: string;
    language: AnnotationLanguage;
    consent_record: {
      consent_id: string;
      community: string;
      verified_by: string;
      revocable: boolean;
    };
    confidence: number;
  }): Promise<AnnotationResult> {
    return this.submitAnnotation({
      entity_id: params.entity_id,
      annotation_type: AnnotationType.INDIGENOUS_KNOWLEDGE,
      language: params.language,
      content: params.content,
      confidence: params.confidence,
      annotator_id: params.consent_record.consent_id,
      annotator_credentials: {
        annotator_type: "INDIGENOUS_ELDER",
        tenure_days: 0,
        accuracy_history: 0.5,
        jurisdictions: [],
        languages: [params.language],
        indigenous_consent_id: params.consent_record.consent_id,
        stake_weight_multiplier: 2.5,
      },
      cultural_context: { community: params.consent_record.community },
      consent_verified: true,
    });
  }

  /**
   * Get the Conscious plane (K) contribution for an entity.
   */
  async getConsciousScore(entityId: string): Promise<{ k_score: number; annotator_count: number; languages_represented: number }> {
    const response = await this.request(`/api/v1/planes/conscious/${entityId}`);
    if (!response.ok) return { k_score: 0, annotator_count: 0, languages_represented: 0 };
    return response.json();
  }
}

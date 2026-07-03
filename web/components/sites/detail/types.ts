export type SiteDetail = {
  site_id: string;
  name?: string | null;
  url: string;
  status: string;
  pages_crawled: number;
  pages_indexed: number;
  total_pages: number;
};

export type AppearanceConfig = {
  primary_color: string;
  chat_title: string;
  welcome_message: string;
  bot_avatar_url?: string | null;
  position: string;
  hide_branding: boolean;
  custom_branding_text?: string | null;
  custom_branding_url?: string | null;
};

export type BehaviorConfig = {
  system_prompt: string;
  temperature: number;
  max_tokens: number;
  show_sources: boolean;
};

export type SiteConfig = {
  appearance: AppearanceConfig;
  behavior: BehaviorConfig;
  lead_capture: {
    collect_email: boolean;
    email_required: boolean;
    email_prompt: string;
    collect_name: boolean;
    name_required: boolean;
    capture_timing: string;
    messages_before_capture: number;
  };
  security: {
    allowed_domains: string[];
    enforce_domain_validation: boolean;
    require_referrer: boolean;
    rate_limit_per_session: number;
  };
  quick_prompts: {
    enabled: boolean;
    prompts: Array<{
      id: string;
      text: string;
      icon?: string | null;
      enabled: boolean;
    }>;
    show_after_response: boolean;
    max_display: number;
  };
};

export type CrawlHistory = {
  job_id?: string;
  trigger: string;
  status: string;
  pages_crawled: number;
  pages_indexed: number;
  created_at?: string;
  started_at?: string;
  completed_at?: string | null;
  duration_seconds?: number | null;
};

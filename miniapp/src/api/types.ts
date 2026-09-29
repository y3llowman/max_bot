import type { IconName } from "../components/icons";

export type TaskStatus = "overdue" | "soon" | "planned" | "done";

export interface Task {
  id: string;
  title: string;
  subtitle: string;
  status: TaskStatus;
  due?: string;
  periodicity?: string;
  listed?: boolean;
}

export type DatedTask = Task & { due: string };

export interface TaskSection {
  id: string;
  icon: IconName;
  title: string;
  caption: string;
  body?: string[];
  steps?: string[];
  link?: { label: string; url: string };
}

export interface TaskDetails extends Task {
  heading: string;
  sections: TaskSection[];
  document?: boolean;
  submittedNote?: string;
  done?: { title: string; text: string };
  next?: Task;
}

export interface Counters {
  overdue: number;
  soon: number;
  done: number;
}

export interface DashboardData {
  counters: Counters;
  tasks: Task[];
  nextDue?: string;
  unread: boolean;
  savedAt?: string;
}

export interface Company {
  name: string;
  fullName: string;
  initials: string;
  regime: string;
  inn: string;
  kpp?: string;
  ogrn: string;
  okved?: string;
  category?: string;
  headcount?: string;
  region?: string;
  needsAnswers?: boolean;
  source: { name: string; demo: boolean; updatedAt: string };
  benefits?: Benefit[];
}

export interface Benefit {
  title: string;
  basis: string;
  url: string;
}

export interface FeedItem {
  id: string;
  title: string;
  subtitle: string;
  sentAt: string;
  due?: string;
  status: "open" | "done" | "muted";
  listed: boolean;
  severity: "critical" | "warning" | "info";
}

export interface Option {
  value: string;
  label: string;
}

export interface ProfileForm {
  isLegalEntity: boolean;
  regime?: string;
  headcount?: string;
  registryHeadcount?: number;
  okved: string;
  registryOkved: string;
  region: string;
  registryRegion: string;
  hasLicenses: boolean;
  flags: Record<string, boolean | null>;
  patentFrom?: string;
  patentTo?: string;
  options: { regimes: Option[]; headcounts: Option[]; regions: Option[]; flags: Option[] };
}

export interface ProfileUpdate {
  regime: string | null;
  headcount: string | null;
  okved: string;
  region: string;
  hasLicenses: boolean;
  flags: Record<string, boolean | null>;
  patentFrom: string | null;
  patentTo: string | null;
}

export type RemindMode = "d30-7-1" | "d7-3-1" | "d3-0" | "d0";

export interface NotificationSettings {
  chat: boolean;
  push: boolean;
  email: boolean;
  emailAddress?: string;
  quiet: boolean;
  quietRange: string;
  remind: RemindMode;
}

import type {
  Company, DashboardData, DatedTask, FeedItem, NotificationSettings, ProfileForm, ProfileUpdate, TaskDetails,
} from "./types";

export type ApiErrorCode = "not_found" | "network" | "server" | "unavailable" | "unauthorized" | "conflict" | "invalid";

export class ApiError extends Error {
  code: ApiErrorCode;
  constructor(code: ApiErrorCode, message: string) {
    super(message);
    this.code = code;
  }
}

export interface Api {
  session(): Promise<Company | null>;
  connect(inn: string): Promise<Company>;
  dashboard(): Promise<DashboardData>;
  task(id: string): Promise<TaskDetails>;
  calendar(from: string, to: string): Promise<DatedTask[]>;
  company(): Promise<Company>;
  refreshCompany(): Promise<Company>;
  notifications(): Promise<NotificationSettings>;
  saveNotifications(settings: NotificationSettings): Promise<void>;
  markNotificationsSeen(): Promise<void>;
  feed(): Promise<FeedItem[]>;
  profileForm(): Promise<ProfileForm>;
  saveProfile(update: ProfileUpdate): Promise<Company>;
  addToList(id: string): Promise<void>;
  markSubmitted(id: string): Promise<void>;
  undoSubmitted(id: string): Promise<void>;
  generateDocument(id: string): Promise<void>;
}

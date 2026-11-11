import { ChatMode } from '../domain/system-status';

/** Puerto: dónde se recuerdan las preferencias del usuario entre visitas. */
export abstract class PreferencesStorage {
  abstract loadMode(): ChatMode;
  abstract saveMode(mode: ChatMode): void;
}

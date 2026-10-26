import { useSettings } from "@/api/queries";
import { type Thresholds, thresholdsOf } from "./verdict";

/** The rules runs are judged by, from the server's settings. */
export const useThresholds = (): Thresholds => thresholdsOf(useSettings().data?.effective ?? {});

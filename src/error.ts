export const ERR = {
  BAD_TIMESTAMP: "bad_timestamp",
  TIMESTAMP_OUT_OF_WINDOW: "timestamp_out_of_window",
  INVALID_SIGNATURE: "invalid_signature",
  REPLAY_DETECTED: "replay_detected",
  MISSING_SIGNATURE_HEADERS: "missing_signature_headers",
  MISSING_MSG: "missing_msg",
  SERVER_MISCONFIG: "server_misconfig",
} as const;

export type ErrorCode = typeof ERR[keyof typeof ERR];
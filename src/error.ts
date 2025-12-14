export const ERR = {
  BAD_TIMESTAMP: "bad_timestamp",
  REQUEST_TIMEOUT: "request_timeout",
  INVALID_SIGNATURE: "invalid_signature",
  REPLAY_DETECTED: "replay_detected",
  MISSING_SIGNATURE_HEADERS: "missing_signature_headers",
  MISSING_MSG: "missing_msg",
  SERVER_MISCONFIG: "server_error",
} as const;

export type ErrorCode = typeof ERR[keyof typeof ERR];
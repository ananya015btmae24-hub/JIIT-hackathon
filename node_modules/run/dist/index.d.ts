declare const runErrorSymbol: unique symbol;
/**
 * Base class for errors raised by the JavaScript runtime.
 *
 * All package-specific errors include a stable `code` string and may include
 * structured `details` for diagnostics.
 */
declare class RunError extends Error {
    private readonly [runErrorSymbol];
    /** Stable machine-readable error code. */
    code: string;
    /** Optional structured diagnostic details. */
    readonly details?: unknown;
    constructor(message: string, code?: string, details?: unknown);
    /** Identifies `RunError` instances across duplicate package copies. */
    static isInstance(error: unknown): error is RunError;
}

/** Raised when the caller's abort signal aborts a run invocation. */
declare class RunAbortedError extends RunError {
    constructor();
}

/** Base class for failures caused by nested host function execution. */
declare class RunHostFunctionError extends RunError {
    constructor(message: string, details?: unknown);
}

/** Raised when sandboxed code exceeds bridge request limits. */
declare class RunBridgeLimitError extends RunError {
    constructor(message: string, details?: unknown);
}

/**
 * Raised when the process-global worker cap has been reached.
 *
 * Configure the cap with `setMaxWorkers`.
 */
declare class RunConcurrencyError extends RunError {
    constructor(maxWorkers: number);
}

/** Raised when guest JavaScript exceeds its per-invocation CPU time limit. */
declare class RunCpuTimeoutError extends RunError {
    constructor(cpuTimeoutMs: number);
}

/**
 * Raised when sandboxed code starts host bridge work and returns without
 * awaiting or otherwise observing it.
 */
declare class RunDetachedBridgeRequestError extends RunError {
    constructor(message: string, details?: unknown);
}

/**
 * Raised when the main thread and worker protocol observes an invalid or
 * mismatched message.
 */
declare class RunProtocolError extends RunError {
    constructor(message: string, details?: unknown);
}

/** Raised when the provided source exceeds `limits.maxSourceBytes`. */
declare class RunSourceTooLargeError extends RunError {
    constructor(bytes: number, maxBytes: number);
}

/** Raised when a sandbox invocation exceeds its timeout. */
declare class RunTimeoutError extends RunError {
    constructor(timeoutMs: number);
}

/**
 * A host function made available to sandboxed JavaScript.
 */
type HostFunction<ARGUMENTS extends unknown[] = unknown[], OUTPUT = unknown> = (...args: ARGUMENTS) => OUTPUT | Promise<OUTPUT>;
/**
 * Context supplied to each host function invocation.
 */
interface HostFunctionContext {
    /** Signal aborted when the run is aborted, times out, or fails. */
    abortSignal: AbortSignal;
    /** Stable identifier for the current run attempt. */
    invocationId: string;
    /** Stable identifier for the logical run across every replay attempt. */
    logicalRunId: string;
    /** Stable identifier for this host function request within the run attempt. */
    requestId: string;
    /** One-based request order within the run attempt. */
    requestIndex: number;
    /** Fully qualified host function path, for example `tools.search`. */
    hostFunctionName: string;
    /** Interrupts this host function and suspends the run. */
    interrupt(payload: unknown): never;
    /** Present when an interrupted host function is reinvoked during replay. */
    resume?: HostFunctionResumeContext;
}
interface HostFunctionResumeContext {
    interruptionId: string;
    payload: unknown;
    resolution: unknown;
}
/** A named collection of host functions. */
type HostFunctionGroup = Record<string, HostFunction<never[], unknown>>;
/**
 * Host function groups installed as guest globals.
 *
 * A group named `tools` containing `search` is called as `tools.search()` in
 * sandboxed code.
 */
type HostFunctions = Record<string, HostFunctionGroup>;
/** Host functions exposed to guest JavaScript with synchronous call semantics. */
type SyncHostFunctions = HostFunctions;
/** Native ES module resolver used by QuickJS. */
interface RunModuleLoader {
    /** Stable identity authenticated by continuations that use this loader. */
    identity?: string;
    /** Resolve a raw specifier relative to its importing module. */
    normalize?(specifier: string, importer: string): string | Promise<string>;
    /** Return source code for a normalized module specifier. */
    load(specifier: string): string | Promise<string>;
}
/** Resource limits applied to one sandbox invocation. */
interface RunLimits {
    /**
     * Wall-clock ceiling for the complete invocation, including time spent
     * waiting on host functions, module loaders, and continuation codecs.
     * Exceeding it fails with `RUN_TIMEOUT`.
     *
     * @default `30_000`
     */
    timeoutMs?: number;
    /**
     * Time the worker may spend running guest JavaScript in one invocation.
     * Time spent awaiting asynchronous host functions or blocked in synchronous
     * host functions and module loaders does not count. Each invocation,
     * including each continuation resume, starts with a fresh budget. Exceeding
     * it fails with `RUN_CPU_TIMEOUT`.
     *
     * This measures elapsed time while guest code runs, so it approximates CPU
     * time rather than reading per-thread CPU counters. Guest time never exceeds
     * wall time, so this limit only takes effect when it is lower than
     * `timeoutMs`.
     *
     * @default `10_000`
     */
    cpuTimeoutMs?: number;
    /** @default `64 * 1024 * 1024` */
    memoryLimitBytes?: number;
    /** @default `2 * 1024 * 1024` */
    maxStackSizeBytes?: number;
    /** @default `1024 * 1024` */
    maxResultBytes?: number;
    /** @default `64 * 1024` */
    maxConsoleOutputBytes?: number;
    /** @default `256 * 1024` */
    maxSourceBytes?: number;
    /** @default `1024 * 1024` */
    maxHostFunctionArgumentsBytes?: number;
    /** @default `4 * 1024 * 1024` */
    maxHostFunctionOutputBytes?: number;
    /** @default `256` */
    maxBridgeRequests?: number;
    /** @default `32` */
    maxInFlightBridgeRequests?: number;
    /** @default `32 * 1024 * 1024` */
    maxContinuationBytes?: number;
}
/** Shared defaults used by a runner. */
interface RunnerOptions<TOKEN = string> {
    limits?: RunLimits;
    /** Host functions exposed with synchronous guest call semantics. */
    syncHostFunctions?: SyncHostFunctions;
    /** HMAC key used for signed continuations. Cannot be combined with continuationCodec. */
    continuationSecret?: string | Uint8Array;
    continuationCodec?: ContinuationCodec<TOKEN>;
    /** Authenticated application/endpoint audience for every continuation. */
    continuationAudience?: string;
}
/** How the entry source is evaluated. */
type RunSourceType = 'function-body' | 'module';
/** Input accepted by `run` and `Runner.run`. */
interface RunInput<TOKEN = unknown> {
    /**
     * JavaScript or type-stripped TypeScript function-body source. Runtime type
     * stripping is used when provided natively by Node or Bun, or through the
     * optional TypeScript peer dependency on Node 20.
     * Top-level `await` and `return` are supported.
     */
    source: string;
    /**
     * Entry-source evaluation mode. A function body supports top-level `await`
     * and `return`; a module supports static imports and has no return value.
     * Defaults to `module` when `moduleLoader` is present and `function-body`
     * otherwise.
     */
    sourceType?: RunSourceType;
    hostFunctions?: HostFunctions;
    /**
     * Optional native ES module loader. It enables native dynamic imports in a
     * function body and static and dynamic imports in a module.
     */
    moduleLoader?: RunModuleLoader;
    abortSignal?: AbortSignal;
    limits?: RunLimits;
    continuation?: TOKEN;
    /**
     * Resolutions for a non-empty subset of pending interruptions. Required when
     * resuming a continuation; interruptions without a resolution remain pending.
     */
    resolutions?: RunResolution[];
    /**
     * Serializable tenant, principal, or policy context authenticated by a
     * continuation and required unchanged when it is resumed.
     */
    continuationContext?: unknown;
}
/** Result of a completed sandbox invocation. */
interface RunCompletedResult<OUTPUT = unknown> {
    status: 'completed';
    value: OUTPUT;
}
interface RunInterruption<PAYLOAD = unknown> {
    id: string;
    hostFunctionName: string;
    /** Complete guest argument list for the interrupted host function call. */
    arguments: unknown[];
    payload: PAYLOAD;
}
interface RunInterruptedResult<TOKEN = unknown> {
    status: 'interrupted';
    interruptions: RunInterruption[];
    /** Opaque bearer capability. Persist it without modifying it. */
    continuation: TOKEN;
}
interface RunResolution<VALUE = unknown> {
    interruptionId: string;
    value: VALUE;
}
/**
 * Result of a sandbox invocation.
 */
type RunResult<OUTPUT = unknown, TOKEN = unknown> = RunCompletedResult<OUTPUT> | RunInterruptedResult<TOKEN>;
interface ContinuationCodec<TOKEN = unknown> {
    encode(state: RunContinuationState, context?: ContinuationOperationContext): TOKEN | Promise<TOKEN>;
    decode(token: TOKEN, context?: ContinuationOperationContext): RunContinuationState | Promise<RunContinuationState>;
    /**
     * Optionally acquires a continuation for validation before consuming it.
     * The runtime commits valid continuations and rolls back failed or cancelled
     * decode attempts.
     */
    decodeTransaction?(token: TOKEN, context?: ContinuationOperationContext): ContinuationDecodeTransaction | Promise<ContinuationDecodeTransaction>;
}
interface ContinuationDecodeTransaction {
    state: RunContinuationState;
    commit(): void | Promise<void>;
    rollback(): void | Promise<void>;
}
interface ContinuationOperationContext {
    abortSignal: AbortSignal;
    deadlineMs: number;
}
/** Serializable replay state passed to a configured continuation codec. */
interface RunContinuationState {
    version: 2;
    runtime: 'run-replay-v2';
    /** Present for workflows using aggregate attempt accounting; absent on legacy state. */
    bridgeRequestLimits?: {
        maxBridgeRequests: number;
        maxHostFunctionArgumentsBytes: number;
    };
    serde: 'run-js-v1';
    source: string;
    logicalRunId: string;
    scopeHash: string;
    determinism: RunDeterminismState;
    ledger: RunLedgerEntry[];
}
interface RunDeterminismState {
    /** Initial Unix timestamp used by deterministic guest date APIs. */
    dateNowMs: number;
    /** 128-bit seed used by deterministic guest `Math.random()`. */
    randomSeed: string;
}
/**
 * One recorded host function outcome in a continuation ledger.
 *
 * The `bindingName` property name is part of the persisted continuation wire
 * format and must remain stable across package releases.
 */
type RunLedgerEntry = {
    bindingName: string;
    inputJson: string;
    status: 'fulfilled';
    settledOrder: number;
    dateNowMs: number;
    valueJson: string;
} | {
    bindingName: string;
    inputJson: string;
    status: 'rejected';
    settledOrder: number;
    dateNowMs: number;
    error: SerializableError;
} | {
    bindingName: string;
    inputJson: string;
    status: 'interrupted';
    interruptionId: string;
    payloadJson: string;
} | {
    bridgeKind: 'sync-host' | 'module-normalize' | 'module-load';
    bindingName: string;
    inputJson: string;
    status: 'fulfilled';
    valueJson: string;
} | {
    bridgeKind: 'sync-host' | 'module-normalize' | 'module-load';
    bindingName: string;
    inputJson: string;
    status: 'rejected';
    error: SerializableError;
};
/** Configured JavaScript runner. */
interface Runner<TOKEN = unknown> {
    run<OUTPUT = unknown>(input: RunInput<TOKEN>): Promise<RunResult<OUTPUT, TOKEN>>;
}

interface SignedContinuationCodecOptions {
    /** Primary HMAC key used for new tokens and verification. */
    secret: string | Uint8Array;
    /** Previous HMAC keys accepted only for verification during key rotation. */
    verificationSecrets?: (string | Uint8Array)[];
    maxAgeMs?: number;
    maxTokenBytes?: number;
    /** Allowed positive clock skew for issued-at validation. @defaultValue `60_000` */
    clockSkewMs?: number;
}
interface ContinuationStorage {
    set(key: string, value: StoredContinuation, context?: ContinuationOperationContext): void | Promise<void>;
    /**
     * Atomically claims a continuation without removing it. Claims must become
     * available again after a bounded interval if neither consume nor release runs.
     */
    acquire(key: string, claimId: string, context?: ContinuationOperationContext): StoredContinuation | undefined | Promise<StoredContinuation | undefined>;
    /** Atomically removes a continuation only when its claim identifier matches. */
    consume(key: string, claimId: string): void | Promise<void>;
    /** Atomically releases a continuation only when its claim identifier matches. */
    release(key: string, claimId: string): void | Promise<void>;
}
interface StoredContinuation {
    state: RunContinuationState;
    expiresAtMs: number;
}
declare const createSignedContinuationCodec: (options: SignedContinuationCodecOptions) => ContinuationCodec<string>;
declare const createStoredContinuationCodec: ({ storage, maxAgeMs, }: {
    storage: ContinuationStorage;
    maxAgeMs?: number;
}) => ContinuationCodec<string>;

/** Creates a runner with shared defaults. */
declare const createRunner: <TOKEN = string>(options?: RunnerOptions<TOKEN>) => Runner<TOKEN>;
/** Executes JavaScript in a fresh, hardened QuickJS context. */
declare const run: <OUTPUT = unknown>(input: RunInput<string>) => Promise<RunResult<OUTPUT, string>>;

/** Returns the context for the currently executing host function. */
declare const getHostFunctionContext: () => HostFunctionContext;

/** Returns whether a value is an interrupted run result. */
declare const isRunInterruptedResult: (value: unknown) => value is RunInterruptedResult<unknown>;

/**
 * Sets the process-global maximum number of active run workers.
 *
 * Pass `undefined` or call without an argument to restore the dynamic
 * memory-based default. The default admits at least one invocation and admits
 * additional workers only when available memory can cover another worker.
 *
 * @param maxWorkers - Positive integer worker cap, or `undefined` to reset.
 */
declare const setMaxWorkers: (maxWorkers?: number) => void;

export { type ContinuationCodec, type ContinuationDecodeTransaction, type ContinuationOperationContext, type ContinuationStorage, type HostFunction, type HostFunctionContext, type HostFunctionGroup, type HostFunctionResumeContext, type HostFunctions, RunAbortedError, RunBridgeLimitError, type RunCompletedResult, RunConcurrencyError, type RunContinuationState, RunCpuTimeoutError, RunDetachedBridgeRequestError, RunError, RunHostFunctionError, type RunInput, type RunInterruptedResult, type RunInterruption, type RunLedgerEntry, type RunLimits, type RunModuleLoader, RunProtocolError, type RunResolution, type RunResult, RunSourceTooLargeError, type RunSourceType, RunTimeoutError, type Runner, type RunnerOptions, type SignedContinuationCodecOptions, type StoredContinuation, type SyncHostFunctions, createRunner, createSignedContinuationCodec, createStoredContinuationCodec, getHostFunctionContext, isRunInterruptedResult, run, setMaxWorkers };

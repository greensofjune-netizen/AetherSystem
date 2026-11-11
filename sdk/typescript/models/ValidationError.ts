/**
 * FastAPI request validation error. Kept separately from generated models because
 * the generator incorrectly maps the string/integer location union.
 */
export interface ValidationError {
    loc: Array<string | number>;
    msg: string;
    type: string;
    input?: unknown;
    ctx?: Record<string, unknown> | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
    const prototype = Object.getPrototypeOf(value);
    return prototype === Object.prototype || prototype === null;
}

export function instanceOfValidationError(value: unknown): value is ValidationError {
    if (!isRecord(value)) return false;
    const entry = value;
    return Array.isArray(entry.loc)
        && Array.from(entry.loc).every((part: unknown) =>
            typeof part === 'string' || (typeof part === 'number' && Number.isInteger(part)))
        && typeof entry.msg === 'string'
        && typeof entry.type === 'string'
        && (entry.ctx === undefined || entry.ctx === null || isRecord(entry.ctx));
}

export function ValidationErrorFromJSON(json: unknown): ValidationError {
    return ValidationErrorFromJSONTyped(json, false);
}

export function ValidationErrorFromJSONTyped(json: unknown, _ignoreDiscriminator: boolean): ValidationError {
    if (!instanceOfValidationError(json)) throw new TypeError('Invalid validation error response.');
    return {
        loc: [...json.loc],
        msg: json.msg,
        type: json.type,
        ...(Object.prototype.hasOwnProperty.call(json, 'input') ? { input: json.input } : {}),
        ...(Object.prototype.hasOwnProperty.call(json, 'ctx') ? { ctx: json.ctx } : {}),
    };
}

export function ValidationErrorToJSON(value: ValidationError): ValidationError {
    return ValidationErrorToJSONTyped(value, false);
}

export function ValidationErrorToJSONTyped(value: ValidationError, _ignoreDiscriminator = false): ValidationError {
    if (!instanceOfValidationError(value)) throw new TypeError('Invalid validation error.');
    return {
        loc: [...value.loc],
        msg: value.msg,
        type: value.type,
        ...(Object.prototype.hasOwnProperty.call(value, 'input') ? { input: value.input } : {}),
        ...(Object.prototype.hasOwnProperty.call(value, 'ctx') ? { ctx: value.ctx } : {}),
    };
}

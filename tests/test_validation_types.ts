import {
  instanceOfValidationError,
  ValidationErrorFromJSON,
  ValidationErrorToJSON,
  type ValidationError,
} from '../sdk/typescript/models/ValidationError.ts';

const valid: ValidationError = {
  loc: ['body', 'items', 0, 'name'],
  msg: 'Field required',
  type: 'missing',
  input: null,
};

// @ts-expect-error Locations are strings or integers, not booleans.
const invalid: ValidationError = { ...valid, loc: [true] };

void invalid;

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const response = { ...valid, extra: true };
const parsed = ValidationErrorFromJSON(response);
assert(instanceOfValidationError(parsed), 'Expected a valid validation error.');
assert(parsed !== response, 'Parsing should return a new object.');
assert(!('extra' in parsed), 'Parsing should omit unknown properties.');
assert(parsed.input === null, 'Parsing should preserve nullable input.');
assert(
  !instanceOfValidationError({ ...valid, loc: Array(1) }),
  'Sparse location arrays should be rejected.',
);
assert(
  !instanceOfValidationError({ ...valid, ctx: new Date() }),
  'Non-record context values should be rejected.',
);
assert(ValidationErrorToJSON(parsed) !== parsed, 'Serialization should return a new object.');

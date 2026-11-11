# ValidationError

A request-validation issue returned in the `detail` array of a FastAPI 422
response. The location contains string field names and integer array indices.

| Property | Type | Meaning |
| --- | --- | --- |
| `loc` | `Array<string \| number>` | Location of the invalid input, such as `["body", "items", 0, "name"]`. |
| `msg` | `string` | Human-readable explanation. |
| `type` | `string` | Machine-readable validation code. |
| `input` | `unknown` (optional) | Rejected input, which can contain sensitive data. |
| `ctx` | `Record<string, unknown> \| null` (optional) | Additional validation context. |

```typescript
import { instanceOfValidationError, type ValidationError } from '../models/ValidationError';

const example: ValidationError = {
  loc: ['body', 'items', 0, 'name'],
  msg: 'Field required',
  type: 'missing',
};

if (instanceOfValidationError(example)) console.log(example.loc, example.msg);
```

The JSON conversion helpers validate the required fields and return a new object
containing only the documented properties. `loc` must be a dense array of
strings and integers; `ctx`, when present, must be a plain object or `null`.

Not every 422 response uses this shape: application errors may instead return
`{"detail": "message"}`. Do not log or display `input` or `ctx` indiscriminately.
The SDK's `ResponseError` retains the response for callers to inspect.

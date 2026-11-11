
# UnifiedEnvelope


## Properties

Name | Type
------------ | -------------
`protocolVersion` | string
`sourceLang` | string
`node` | string
`event` | string
`timestamp` | number
`payload` | { [key: string]: any; }

## Example

```typescript
import type { UnifiedEnvelope } from ''

// TODO: Update the object below with actual values
const example = {
  "protocolVersion": null,
  "sourceLang": null,
  "node": null,
  "event": null,
  "timestamp": null,
  "payload": null,
} satisfies UnifiedEnvelope

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as UnifiedEnvelope
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


# UnifiedDispatchResponse


## Properties

Name | Type
------------ | -------------
`status` | string
`persisted` | boolean
`eventId` | number
`liveSubscribersNotified` | number

## Example

```typescript
import type { UnifiedDispatchResponse } from ''

// TODO: Update the object below with actual values
const example = {
  "status": null,
  "persisted": null,
  "eventId": null,
  "liveSubscribersNotified": null,
} satisfies UnifiedDispatchResponse

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as UnifiedDispatchResponse
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

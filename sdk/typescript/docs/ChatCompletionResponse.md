
# ChatCompletionResponse


## Properties

Name | Type
------------ | -------------
`model` | string
`response` | string
`status` | string
`tokensUsed` | number

## Example

```typescript
import type { ChatCompletionResponse } from ''

// TODO: Update the object below with actual values
const example = {
  "model": null,
  "response": null,
  "status": null,
  "tokensUsed": null,
} satisfies ChatCompletionResponse

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as ChatCompletionResponse
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

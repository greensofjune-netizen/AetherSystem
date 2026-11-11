
# TaskCreate


## Properties

Name | Type
------------ | -------------
`title` | string
`description` | string
`priority` | string
`dueDate` | string

## Example

```typescript
import type { TaskCreate } from ''

// TODO: Update the object below with actual values
const example = {
  "title": null,
  "description": null,
  "priority": null,
  "dueDate": null,
} satisfies TaskCreate

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as TaskCreate
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

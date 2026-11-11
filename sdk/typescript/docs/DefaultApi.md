# DefaultApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**completeTaskApiV1TasksTaskIdCompletePost**](DefaultApi.md#completetaskapiv1taskstaskidcompletepost) | **POST** /api/v1/tasks/{task_id}/complete | Complete Task |
| [**createBackupApiV1BackupsPost**](DefaultApi.md#createbackupapiv1backupspost) | **POST** /api/v1/backups | Create Backup |
| [**createBackupScheduleApiV1BackupsSchedulePost**](DefaultApi.md#createbackupscheduleapiv1backupsschedulepost) | **POST** /api/v1/backups/schedule | Create Backup Schedule |
| [**createChatCompletionV1ChatCompletionsPost**](DefaultApi.md#createchatcompletionv1chatcompletionspost) | **POST** /v1/chat/completions | Create Chat Completion |
| [**createEventApiV1EventsPost**](DefaultApi.md#createeventapiv1eventspost) | **POST** /api/v1/events | Create Event |
| [**createTaskApiV1TasksPost**](DefaultApi.md#createtaskapiv1taskspost) | **POST** /api/v1/tasks | Create Task |
| [**deleteBackupScheduleApiV1BackupsScheduleDelete**](DefaultApi.md#deletebackupscheduleapiv1backupsscheduledelete) | **DELETE** /api/v1/backups/schedule | Delete Backup Schedule |
| [**exportProjectApiV1ExportGet**](DefaultApi.md#exportprojectapiv1exportget) | **GET** /api/v1/export | Export Project |
| [**getBackupScheduleApiV1BackupsScheduleGet**](DefaultApi.md#getbackupscheduleapiv1backupsscheduleget) | **GET** /api/v1/backups/schedule | Get Backup Schedule |
| [**healthCheckHealthGet**](DefaultApi.md#healthcheckhealthget) | **GET** /health | Health Check |
| [**listEventsApiV1EventsGet**](DefaultApi.md#listeventsapiv1eventsget) | **GET** /api/v1/events | List Events |
| [**listTasksApiV1TasksGet**](DefaultApi.md#listtasksapiv1tasksget) | **GET** /api/v1/tasks | List Tasks |
| [**projectDoctorApiV1DoctorGet**](DefaultApi.md#projectdoctorapiv1doctorget) | **GET** /api/v1/doctor | Project Doctor |
| [**projectStatusApiV1StatusGet**](DefaultApi.md#projectstatusapiv1statusget) | **GET** /api/v1/status | Project Status |
| [**reopenTaskApiV1TasksTaskIdReopenPost**](DefaultApi.md#reopentaskapiv1taskstaskidreopenpost) | **POST** /api/v1/tasks/{task_id}/reopen | Reopen Task |
| [**restoreProjectApiV1RestorePost**](DefaultApi.md#restoreprojectapiv1restorepost) | **POST** /api/v1/restore | Restore Project |
| [**runCodeProcessGet**](DefaultApi.md#runcodeprocessget) | **GET** /process | Run Code |
| [**serveSharedJavascriptAetherClientJsGet**](DefaultApi.md#servesharedjavascriptaetherclientjsget) | **GET** /aether_client.js | Serve Shared Javascript |
| [**unifiedCrossLanguageDispatchApiV1UnifiedDispatchPost**](DefaultApi.md#unifiedcrosslanguagedispatchapiv1unifieddispatchpost) | **POST** /api/v1/unified/dispatch | Unified Cross Language Dispatch |
| [**unifiedDispatchStateApiV1UnifiedStateGet**](DefaultApi.md#unifieddispatchstateapiv1unifiedstateget) | **GET** /api/v1/unified/state | Unified Dispatch State |
| [**unifiedDispatchStreamApiV1UnifiedStreamGet**](DefaultApi.md#unifieddispatchstreamapiv1unifiedstreamget) | **GET** /api/v1/unified/stream | Unified Dispatch Stream |
| [**updateTaskApiV1TasksTaskIdPatch**](DefaultApi.md#updatetaskapiv1taskstaskidpatch) | **PATCH** /api/v1/tasks/{task_id} | Update Task |



## completeTaskApiV1TasksTaskIdCompletePost

> { [key: string]: any | null; } completeTaskApiV1TasksTaskIdCompletePost(taskId)

Complete Task

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CompleteTaskApiV1TasksTaskIdCompletePostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // number
    taskId: 56,
  } satisfies CompleteTaskApiV1TasksTaskIdCompletePostRequest;

  try {
    const data = await api.completeTaskApiV1TasksTaskIdCompletePost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **taskId** | `number` |  | [Defaults to `undefined`] |

### Return type

**{ [key: string]: any | null; }**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## createBackupApiV1BackupsPost

> { [key: string]: ResponseCreateBackupApiV1BackupsPostValue; } createBackupApiV1BackupsPost(backupRequest)

Create Backup

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CreateBackupApiV1BackupsPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // BackupRequest
    backupRequest: ...,
  } satisfies CreateBackupApiV1BackupsPostRequest;

  try {
    const data = await api.createBackupApiV1BackupsPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **backupRequest** | [BackupRequest](BackupRequest.md) |  | |

### Return type

[**{ [key: string]: ResponseCreateBackupApiV1BackupsPostValue; }**](ResponseCreateBackupApiV1BackupsPostValue.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **201** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## createBackupScheduleApiV1BackupsSchedulePost

> { [key: string]: ResponseCreateBackupApiV1BackupsPostValue; } createBackupScheduleApiV1BackupsSchedulePost(backupRequest)

Create Backup Schedule

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CreateBackupScheduleApiV1BackupsSchedulePostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // BackupRequest
    backupRequest: ...,
  } satisfies CreateBackupScheduleApiV1BackupsSchedulePostRequest;

  try {
    const data = await api.createBackupScheduleApiV1BackupsSchedulePost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **backupRequest** | [BackupRequest](BackupRequest.md) |  | |

### Return type

[**{ [key: string]: ResponseCreateBackupApiV1BackupsPostValue; }**](ResponseCreateBackupApiV1BackupsPostValue.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## createChatCompletionV1ChatCompletionsPost

> ChatCompletionResponse createChatCompletionV1ChatCompletionsPost(chatCompletionRequest)

Create Chat Completion

Generate a completion using the configured local model.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CreateChatCompletionV1ChatCompletionsPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // ChatCompletionRequest
    chatCompletionRequest: ...,
  } satisfies CreateChatCompletionV1ChatCompletionsPostRequest;

  try {
    const data = await api.createChatCompletionV1ChatCompletionsPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **chatCompletionRequest** | [ChatCompletionRequest](ChatCompletionRequest.md) |  | |

### Return type

[**ChatCompletionResponse**](ChatCompletionResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## createEventApiV1EventsPost

> { [key: string]: any | null; } createEventApiV1EventsPost(eventCreate)

Create Event

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CreateEventApiV1EventsPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // EventCreate
    eventCreate: ...,
  } satisfies CreateEventApiV1EventsPostRequest;

  try {
    const data = await api.createEventApiV1EventsPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **eventCreate** | [EventCreate](EventCreate.md) |  | |

### Return type

**{ [key: string]: any | null; }**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **201** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## createTaskApiV1TasksPost

> { [key: string]: any | null; } createTaskApiV1TasksPost(taskCreate)

Create Task

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CreateTaskApiV1TasksPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // TaskCreate
    taskCreate: ...,
  } satisfies CreateTaskApiV1TasksPostRequest;

  try {
    const data = await api.createTaskApiV1TasksPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **taskCreate** | [TaskCreate](TaskCreate.md) |  | |

### Return type

**{ [key: string]: any | null; }**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **201** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## deleteBackupScheduleApiV1BackupsScheduleDelete

> { [key: string]: ResponseHealthCheckHealthGetValue; } deleteBackupScheduleApiV1BackupsScheduleDelete()

Delete Backup Schedule

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { DeleteBackupScheduleApiV1BackupsScheduleDeleteRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.deleteBackupScheduleApiV1BackupsScheduleDelete();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters

This endpoint does not need any parameter.

### Return type

[**{ [key: string]: ResponseHealthCheckHealthGetValue; }**](ResponseHealthCheckHealthGetValue.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## exportProjectApiV1ExportGet

> { [key: string]: any | null; } exportProjectApiV1ExportGet()

Export Project

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ExportProjectApiV1ExportGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.exportProjectApiV1ExportGet();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters

This endpoint does not need any parameter.

### Return type

**{ [key: string]: any | null; }**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getBackupScheduleApiV1BackupsScheduleGet

> { [key: string]: any | null; } getBackupScheduleApiV1BackupsScheduleGet()

Get Backup Schedule

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetBackupScheduleApiV1BackupsScheduleGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.getBackupScheduleApiV1BackupsScheduleGet();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters

This endpoint does not need any parameter.

### Return type

**{ [key: string]: any | null; }**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## healthCheckHealthGet

> { [key: string]: ResponseHealthCheckHealthGetValue; } healthCheckHealthGet()

Health Check

Report server health and whether the configured model file is present.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { HealthCheckHealthGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.healthCheckHealthGet();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters

This endpoint does not need any parameter.

### Return type

[**{ [key: string]: ResponseHealthCheckHealthGetValue; }**](ResponseHealthCheckHealthGetValue.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## listEventsApiV1EventsGet

> Array&lt;{ [key: string]: any; }&gt; listEventsApiV1EventsGet(limit, search, topic, since, until)

List Events

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ListEventsApiV1EventsGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // number (optional)
    limit: 56,
    // string (optional)
    search: search_example,
    // string (optional)
    topic: topic_example,
    // string (optional)
    since: since_example,
    // string (optional)
    until: until_example,
  } satisfies ListEventsApiV1EventsGetRequest;

  try {
    const data = await api.listEventsApiV1EventsGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **limit** | `number` |  | [Optional] [Defaults to `20`] |
| **search** | `string` |  | [Optional] [Defaults to `undefined`] |
| **topic** | `string` |  | [Optional] [Defaults to `undefined`] |
| **since** | `string` |  | [Optional] [Defaults to `undefined`] |
| **until** | `string` |  | [Optional] [Defaults to `undefined`] |

### Return type

**Array<{ [key: string]: any; }>**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## listTasksApiV1TasksGet

> Array&lt;{ [key: string]: any | null; }&gt; listTasksApiV1TasksGet(status, search)

List Tasks

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ListTasksApiV1TasksGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // 'pending' | 'done' (optional)
    status: status_example,
    // string (optional)
    search: search_example,
  } satisfies ListTasksApiV1TasksGetRequest;

  try {
    const data = await api.listTasksApiV1TasksGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **status** | `pending`, `done` |  | [Optional] [Defaults to `undefined`] [Enum: pending, done] |
| **search** | `string` |  | [Optional] [Defaults to `undefined`] |

### Return type

**Array<{ [key: string]: any | null; }>**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## projectDoctorApiV1DoctorGet

> { [key: string]: any | null; } projectDoctorApiV1DoctorGet()

Project Doctor

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ProjectDoctorApiV1DoctorGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.projectDoctorApiV1DoctorGet();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters

This endpoint does not need any parameter.

### Return type

**{ [key: string]: any | null; }**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## projectStatusApiV1StatusGet

> { [key: string]: any | null; } projectStatusApiV1StatusGet(limit)

Project Status

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ProjectStatusApiV1StatusGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // number (optional)
    limit: 56,
  } satisfies ProjectStatusApiV1StatusGetRequest;

  try {
    const data = await api.projectStatusApiV1StatusGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **limit** | `number` |  | [Optional] [Defaults to `3`] |

### Return type

**{ [key: string]: any | null; }**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## reopenTaskApiV1TasksTaskIdReopenPost

> { [key: string]: any | null; } reopenTaskApiV1TasksTaskIdReopenPost(taskId)

Reopen Task

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ReopenTaskApiV1TasksTaskIdReopenPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // number
    taskId: 56,
  } satisfies ReopenTaskApiV1TasksTaskIdReopenPostRequest;

  try {
    const data = await api.reopenTaskApiV1TasksTaskIdReopenPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **taskId** | `number` |  | [Defaults to `undefined`] |

### Return type

**{ [key: string]: any | null; }**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## restoreProjectApiV1RestorePost

> { [key: string]: ResponseRestoreProjectApiV1RestorePostValue; } restoreProjectApiV1RestorePost(restoreRequest)

Restore Project

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { RestoreProjectApiV1RestorePostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // RestoreRequest
    restoreRequest: ...,
  } satisfies RestoreProjectApiV1RestorePostRequest;

  try {
    const data = await api.restoreProjectApiV1RestorePost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **restoreRequest** | [RestoreRequest](RestoreRequest.md) |  | |

### Return type

[**{ [key: string]: ResponseRestoreProjectApiV1RestorePostValue; }**](ResponseRestoreProjectApiV1RestorePostValue.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## runCodeProcessGet

> { [key: string]: string | null; } runCodeProcessGet(inputData)

Run Code

Process text supplied as the input_data query parameter.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { RunCodeProcessGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string | Text to process.
    inputData: inputData_example,
  } satisfies RunCodeProcessGetRequest;

  try {
    const data = await api.runCodeProcessGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **inputData** | `string` | Text to process. | [Defaults to `undefined`] |

### Return type

**{ [key: string]: string | null; }**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## serveSharedJavascriptAetherClientJsGet

> any serveSharedJavascriptAetherClientJsGet()

Serve Shared Javascript

Serve the shared client to loopback callers.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ServeSharedJavascriptAetherClientJsGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.serveSharedJavascriptAetherClientJsGet();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters

This endpoint does not need any parameter.

### Return type

**any**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## unifiedCrossLanguageDispatchApiV1UnifiedDispatchPost

> UnifiedDispatchResponse unifiedCrossLanguageDispatchApiV1UnifiedDispatchPost(unifiedEnvelope)

Unified Cross Language Dispatch

Persist a cross-language event, update state, and notify live subscribers.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { UnifiedCrossLanguageDispatchApiV1UnifiedDispatchPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // UnifiedEnvelope
    unifiedEnvelope: ...,
  } satisfies UnifiedCrossLanguageDispatchApiV1UnifiedDispatchPostRequest;

  try {
    const data = await api.unifiedCrossLanguageDispatchApiV1UnifiedDispatchPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **unifiedEnvelope** | [UnifiedEnvelope](UnifiedEnvelope.md) |  | |

### Return type

[**UnifiedDispatchResponse**](UnifiedDispatchResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## unifiedDispatchStateApiV1UnifiedStateGet

> { [key: string]: any | null; } unifiedDispatchStateApiV1UnifiedStateGet()

Unified Dispatch State

Return in-memory dashboard state with the durable latest dispatch.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { UnifiedDispatchStateApiV1UnifiedStateGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.unifiedDispatchStateApiV1UnifiedStateGet();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters

This endpoint does not need any parameter.

### Return type

**{ [key: string]: any | null; }**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## unifiedDispatchStreamApiV1UnifiedStreamGet

> any unifiedDispatchStreamApiV1UnifiedStreamGet(lastEventID)

Unified Dispatch Stream

Stream dispatches with durable replay after reconnects and restarts.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { UnifiedDispatchStreamApiV1UnifiedStreamGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string (optional)
    lastEventID: lastEventID_example,
  } satisfies UnifiedDispatchStreamApiV1UnifiedStreamGetRequest;

  try {
    const data = await api.unifiedDispatchStreamApiV1UnifiedStreamGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **lastEventID** | `string` |  | [Optional] [Defaults to `undefined`] |

### Return type

**any**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## updateTaskApiV1TasksTaskIdPatch

> { [key: string]: any | null; } updateTaskApiV1TasksTaskIdPatch(taskId, taskUpdate)

Update Task

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { UpdateTaskApiV1TasksTaskIdPatchRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // number
    taskId: 56,
    // TaskUpdate
    taskUpdate: ...,
  } satisfies UpdateTaskApiV1TasksTaskIdPatchRequest;

  try {
    const data = await api.updateTaskApiV1TasksTaskIdPatch(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **taskId** | `number` |  | [Defaults to `undefined`] |
| **taskUpdate** | [TaskUpdate](TaskUpdate.md) |  | |

### Return type

**{ [key: string]: any | null; }**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

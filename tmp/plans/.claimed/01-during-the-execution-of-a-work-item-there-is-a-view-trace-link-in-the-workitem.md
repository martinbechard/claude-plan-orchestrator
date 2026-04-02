# During the execution of a work item, there is a view trace link in the workitem 

## Status: Open

## Priority: Medium

## Summary

During the execution of a work item, there is a view trace link in the workitem detail page, but when I click on view trace, I get: {“detail”:“Not Found”} instead of a web page. Expected: the detailed trace for the work item

## Source

Created from Slack message by U0AEWQYSLF9 at 1775164871.322879.

## LangSmith Trace: f63374b7-89e4-463d-adc5-4265ab5c9c95


## 5 Whys Analysis

Title: Trace link returns 404 instead of displaying detailed trace

Clarity: 3/5

5 Whys:

W1: Why is clicking the trace link returning a "Not Found" error?
    Because: The HTTP request to the backend is returning a 404 response, indicating the endpoint cannot find the requested trace resource [C2]

W2: Why can't the backend find the trace resource?
    Because: Either the trace URL is malformed, the trace ID is invalid, or the backend endpoint for retrieving traces hasn't been implemented [C2] [ASSUMPTION]

W3: Why would the trace ID be invalid when a valid LangSmith trace exists in the system?
    Because: There's a disconnect between how the trace link is generated on the frontend [C1] and how it should map to the actual LangSmith trace ID [C7] [ASSUMPTION]

W4: Why does this mapping disconnect exist?
    Because: The frontend link generation and backend endpoint implementation are either inconsistent or one of them is missing entirely [C1, C2] [ASSUMPTION]

W5: Why does this need to be fixed?
    Because: Users need to access detailed execution traces to understand work item behavior [C3], and this is blocking visibility into the LangSmith trace data [C7] that the system is already capturing [C1]

Root Need: The system must establish a working path from frontend trace links [C1] to backend trace retrieval that successfully returns trace details [C2, C3] instead of 404 errors, enabling users to access LangSmith trace data during work item execution

Summary: A missing or misaligned integration between frontend trace links and backend trace retrieval is preventing users from accessing execution traces they expect to see.

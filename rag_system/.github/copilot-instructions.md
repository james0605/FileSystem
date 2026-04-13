# GitHub Copilot Instructions — RAG-Augmented Technical Document Search

## When to invoke RAG

Trigger the `search_documents` MCP tool when **any** of the following are true:

- The user message starts with `/rag`
- The question involves: specifications, pin description, register map, timing diagram,
  electrical characteristics, I/O voltage, datasheet, user manual, application note,
  reference manual, errata
- The user explicitly asks to "look up", "check the datasheet", "find in the manual",
  or "refer to the documentation"

Do **not** invoke RAG for general programming questions unrelated to hardware or
product-specific documentation.

---

## Filtering syntax

Users may narrow the search with inline filters:

| Syntax | Example | Effect |
|--------|---------|--------|
| (none) | `/rag how does the SPI interface work` | Search all indexed documents |
| `category:<name>` | `/rag category:stm32 what is the voltage range` | Limit to a specific folder/category |
| `source:<path>` | `/rag source:stm32/rm0433.pdf pin description` | Limit to a single file |

Both filters may be combined:
```
/rag category:sensors source:sensors/bmp390.pdf ODR settings
```

Parse the filters from the user message before calling `search_documents`, then
pass them as the `category` and/or `source` arguments.

---

## How to call the tools

### Search
```
search_documents(
  query="<extracted natural-language query>",
  n_results=5,          # increase to 10 for broad topics
  source="dir1/A.pdf",  # optional
  category="dir1"       # optional
)
```

### List available documents
Call `list_documents()` when the user asks what documents are available or
what categories exist.

---

## Response format

1. **Answer first** — synthesize a direct answer from the retrieved passages.
2. **Cite every claim** using the format `[source/path.pdf, Page N]`  
   Example: `[stm32/rm0433.pdf, Page 142]`
3. **Use code blocks** for register values, voltage levels, timing specs, pin tables, etc.
4. **If information is not found** in the search results, state explicitly:  
   > "This information was not found in the indexed documents."  
   Do **not** guess or hallucinate hardware specifications.
5. If multiple sources are relevant, cite all of them.

### Example response structure
```
The SPI clock speed for this device is up to 50 MHz in master mode [dir1/A.pdf, Page 23].

The relevant register is:

| Field | Bits | Description           |
|-------|------|-----------------------|
| BR    | [5:3]| Baud rate control     |
| CPOL  | [1]  | Clock polarity        |
| CPHA  | [0]  | Clock phase           |

[dir1/A.pdf, Page 24]
```

---

## Important rules

- Never invent pin numbers, register addresses, voltage values, or timing specs.
- Always cite the source path and page number.
- If results look unrelated to the query, say so and suggest the user verify the
  document is indexed (`list_documents()`).

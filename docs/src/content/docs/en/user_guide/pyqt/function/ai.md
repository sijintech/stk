---
title: AI Chat Module
description: AI Chat Module
---
The STK application integrates powerful AI chat functionality, allowing users to interact with AI models, obtain information, and solve problems. This guide will introduce how to set up and use this feature.

## Feature Overview

STK's AI chat functionality provides the following features:

- Support for public and private AI models
- Integration with Ollama local models
- Support for document-based RAG (Retrieval-Augmented Generation) technology
- Customizable system prompts and model parameters
- Ability to save multiple model configurations
- Performance analysis and logging

## Usage Steps

### 1. Select or Configure AI Model

At the top of the chat interface, you can select a pre-configured AI model from the dropdown menu, or use the "+" button to add a new model.


##### Adding a New Model Configuration

Click the "+" button to open the model configuration dialog, where you can configure:

**Basic Settings**
- Configuration Name: Name your configuration
- Model Type: Choose public model (local Ollama) or private model (requires API key)
- Host/Endpoint: Model server address
- Port: Server port (default for Ollama is 11434)
- API Key: Access key for private models
- Model Name: Specific model to use, such as deepseek-coder, gpt-4, etc.

**Advanced Settings**
- Temperature: Controls randomness of output (0-1.0)
- Maximum Output Length: Limits the length of AI responses
- System Prompt: Instructions defining AI behavior and role
- RAG Functionality: Enable document-based question answering

### 2. Connect to the Model

After selecting a configuration, click the "Connect" button to establish a connection with the AI model. When the connection is successful, the status label will change from "Not Connected" to "Connected".

You can also click "Connection Status" to verify the detailed status of the model service and view the list of available models.

### 3. Ask Questions and Chat

Enter your question in the input box at the bottom, then press Enter or click the "Send" button.

The AI will process your question and generate an answer in the chat history area. During the answer generation process, you can see real-time streaming output.

#### Interrupting AI Responses

If you need to stop the currently generating response, you can:

1. Click the "Cancel" button next to the "Send" button while the AI is generating a response
2. Or press the Esc key to interrupt the response generation process

The system will immediately stop generating the current response and display a "[User canceled the response generation]" prompt in the chat history. This is particularly useful when dealing with responses that are too long or when the response direction doesn't meet expectations.

#### Copying Message Content

You can easily copy the content of messages in the conversation:

1. In the chat history area, use the mouse to select the text you want to copy
2. Right-click and select "Copy", or use the keyboard shortcut Ctrl+C (Windows/Linux) or Cmd+C (Mac)
3. Additionally, there is a copy button at the end of each AI response that allows you to copy the entire response content with one click

The copy function supports rich text formatting, including syntax highlighting for code blocks, making it convenient to paste content into other editors while maintaining formatting.

### 4. Using RAG Functionality

RAG (Retrieval-Augmented Generation) functionality allows the AI to answer questions based on specific documents, particularly suitable for answering questions related to software usage.

To use RAG functionality:

1. Enable "Import User Manual (Using RAG Technology)" in the advanced settings of the model configuration
2. Click "Browse..." to select a document in PDF format
3. Save the configuration and connect to the model
4. Ask questions related to the document content

After asking a question, the system will first process the document content, extract relevant information, and then the AI will generate more accurate answers based on this information.

> **Note**: RAG functionality relies on the `sentence-transformers` library and requires appropriate Python environment support.

### 5. Model Configuration Management

You can use the buttons on the interface to manage your model configurations:

- ⚙️ (Settings): Edit the currently selected model configuration
- × (Delete): Delete the currently selected model configuration

All configurations are automatically saved and will still be available the next time you start the application.

## Advanced Options

### System Prompts

System prompts can define the AI assistant's role, knowledge scope, and response style. Example of an effective system prompt:

```
You are a professional engineering technical consultant, specializing in the use of STK software. Please answer questions in a concise and accurate manner, and provide practical code examples when appropriate.
```

### Performance Analysis

In the Analysis and Logs tab, you can enable:

- Performance Analysis: Display response time and output length after each response
- Query Logs: Save all conversations to a log file for later viewing

### Conversation History Management

STK's AI chat functionality provides various ways to manage conversation history:

- **Clear Conversation**: Click the "Clear" button above the chat history area to clear all current conversation content and start a new session
- **Save Conversation**: Click the "Save" button to save the current conversation history as an HTML or plain text file for archiving or sharing
- **Load Conversation**: You can restore previously saved conversation history using the "Load" button

## Troubleshooting

### Connection Issues

If you cannot connect to the model service:

1. Check if the host address and port are correct
2. Verify that the Ollama service is running (for public models)
3. Confirm that the API key is valid (for private models)
4. Use the "Connection Status" button to get more detailed diagnostic information

### Memory Issues

Large models require sufficient system memory. If you encounter memory-related errors:

1. Close other memory-intensive applications
2. Try using a smaller model (e.g., from 13B to 7B)
3. Increase system virtual memory/swap space
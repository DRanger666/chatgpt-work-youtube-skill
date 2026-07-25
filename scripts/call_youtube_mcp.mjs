#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

function usage() {
  console.error(
    'usage: call_youtube_mcp.mjs --install DIR ' +
      '(--list-tools | --tool NAME (--arguments JSON | --arguments-file FILE) ' +
      '[--structured-only])',
  );
}

const argv = process.argv.slice(2);
let install;
let tool;
let argumentsText;
let argumentsFile;
let listTools = false;
let structuredOnly = false;

for (let index = 0; index < argv.length; index += 1) {
  const current = argv[index];
  if (current === '--install') install = argv[++index];
  else if (current === '--tool') tool = argv[++index];
  else if (current === '--arguments') argumentsText = argv[++index];
  else if (current === '--arguments-file') argumentsFile = argv[++index];
  else if (current === '--list-tools') listTools = true;
  else if (current === '--structured-only') structuredOnly = true;
  else {
    usage();
    process.exit(2);
  }
}

if (!install || (listTools === Boolean(tool))) {
  usage();
  process.exit(2);
}
if (argumentsText && argumentsFile) {
  usage();
  process.exit(2);
}

install = fs.realpathSync(install);
const node = path.join(install, 'runtime', 'bin', 'node');
const server = path.join(install, 'app', 'dist', 'stdio-server.js');
const sdkRoot = path.join(
  install,
  'app',
  'node_modules',
  '@modelcontextprotocol',
  'sdk',
  'dist',
  'esm',
);

const { Client } = await import(
  pathToFileURL(path.join(sdkRoot, 'client', 'index.js')).href
);
const { StdioClientTransport } = await import(
  pathToFileURL(path.join(sdkRoot, 'client', 'stdio.js')).href
);

const transport = new StdioClientTransport({
  command: node,
  args: [server],
  env: process.env,
  stderr: 'pipe',
});
const client = new Client({
  name: 'work-with-youtube',
  version: '1.0.0',
});

try {
  await client.connect(transport);
  if (listTools) {
    const response = await client.listTools();
    console.log(
      JSON.stringify(
        response.tools.map(({ name, description }) => ({ name, description })),
        null,
        2,
      ),
    );
  } else {
    let toolArguments = {};
    if (argumentsFile) {
      argumentsText = fs.readFileSync(argumentsFile, 'utf8');
    }
    if (argumentsText) {
      toolArguments = JSON.parse(argumentsText);
    }
    const response = await client.callTool({
      name: tool,
      arguments: toolArguments,
    });
    const output =
      structuredOnly && response.structuredContent
        ? response.structuredContent
        : response;
    console.log(JSON.stringify(output, null, 2));
    if (response.isError) process.exitCode = 1;
  }
} finally {
  await client.close();
}

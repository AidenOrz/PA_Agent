/**
 * Test connecting to TRAE ai-agent via @aha-kit/ipc + @aha-kit/rpc.
 *
 * This script uses TRAE's own IPC libraries to connect to the ai-agent
 * process and call the super_completion_query RPC method.
 */

const path = require('path');

// Use TRAE's own node_modules
const TRAE_APP_DIR = 'C:\\Users\\Administrator\\AppData\\Local\\Programs\\TRAE SOLO CN\\resources\\app';
const ipcPath = path.join(TRAE_APP_DIR, 'node_modules', '@aha-kit', 'ipc-win32-x64');
const rpcPath = path.join(TRAE_APP_DIR, 'node_modules', '@aha-kit', 'rpc');

console.log('Loading @aha-kit/ipc-win32-x64 from:', ipcPath);
const ipc = require(ipcPath);
console.log('ipc exports:', Object.keys(ipc));

console.log('\nLoading @aha-kit/rpc from:', rpcPath);
const rpc = require(rpcPath);
console.log('rpc exports:', Object.keys(rpc));

// Check if the ai-agent socket marker file exists
const fs = require('fs');
const os = require('os');
const tmpDir = path.join(os.tmpdir(), 'aha');
console.log('\nTemp dir for AHA IPC:', tmpDir);
try {
    const files = fs.readdirSync(tmpDir);
    console.log('Files in AHA temp dir:', files);
} catch (e) {
    console.log('AHA temp dir does not exist:', e.message);
}

// Try to connect to the ai-agent
async function main() {
    console.log('\n=== Connecting to ai-agent ===');

    try {
        // Connect to the ai-agent IPC server
        const connection = await ipc.connect('ai-agent');
        console.log('Connected to ai-agent!');
        console.log('Connection type:', typeof connection);
        console.log('Connection methods:', Object.getOwnPropertyNames(Object.getPrototypeOf(connection)));

        // Set up message handler
        connection.on('message', (data) => {
            console.log('Received message:', data.toString().substring(0, 500));
        });

        connection.on('connect', () => {
            console.log('Connection established event fired!');
        });

        connection.on('disconnect', () => {
            console.log('Disconnected!');
        });

        connection.on('error', (err) => {
            console.error('Connection error:', err);
        });

        // Wait a bit for connection to establish
        await new Promise(resolve => setTimeout(resolve, 2000));

        // Try sending a healthcheck request
        const requestId = 'test-' + Date.now();
        const healthcheckReq = {
            jsonrpc: '2.0',
            id: requestId,
            method: 'request',
            params: {
                packet_type: 'request',
                session_id: '',
                channel_id: requestId,
                params: {
                    service: 'healthcheck',
                    method: 'ping',
                    data: '',
                    common_params: {},
                    user_info: {
                        name: '',
                        token: '',
                        region: '',
                        is_internal: false,
                        user_id: '',
                        scope: ''
                    },
                    streamlined_common_params: {},
                    client_info: {
                        connect_session_id: ''
                    }
                }
            }
        };

        console.log('\nSending healthcheck request:', JSON.stringify(healthcheckReq).substring(0, 200));
        connection.send(JSON.stringify(healthcheckReq));

        // Wait for response
        await new Promise(resolve => setTimeout(resolve, 5000));

        console.log('\nDone. Closing connection.');
        if (connection.close) {
            connection.close();
        }
    } catch (e) {
        console.error('Failed to connect:', e.message);
        console.error(e.stack);
    }

    process.exit(0);
}

main();

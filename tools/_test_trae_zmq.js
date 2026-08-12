/**
 * Test direct ZMQ connection to TRAE ai-agent.
 * Bypasses the marker file check and connects directly.
 */
const path = require('path');
const fs = require('fs');
const os = require('os');

const TRAE_APP_DIR = 'C:\\Users\\Administrator\\AppData\\Local\\Programs\\TRAE SOLO CN\\resources\\app';

// Load ZMQ from TRAE's node_modules
const zmqAdapterPath = path.join(TRAE_APP_DIR, 'node_modules', '@aha-kit', 'ipc-win32-x64', 'dist', 'zmq-adapter.js');
console.log('Loading zmq-adapter from:', zmqAdapterPath);
const zmqAdapter = require(zmqAdapterPath);
console.log('zmq-adapter exports:', Object.keys(zmqAdapter));

// Generate IPC address (same as @aha-kit/ipc)
const ahaDir = path.join(os.tmpdir(), 'aha');
const socketPath = path.join(ahaDir, 'ai-agent.sock');
const ipcAddress = `ipc://${socketPath}`;
console.log('IPC address:', ipcAddress);
console.log('Socket path:', socketPath);

// Create the aha directory if it doesn't exist
if (!fs.existsSync(ahaDir)) {
    fs.mkdirSync(ahaDir, { recursive: true });
    console.log('Created aha directory:', ahaDir);
}

// Create marker file (to bypass client check)
const markerPath = `${socketPath}.ready`;
if (!fs.existsSync(markerPath)) {
    fs.writeFileSync(markerPath, String(process.pid));
    console.log('Created marker file:', markerPath);
}

async function main() {
    try {
        // Try loading zeromq
        let Dealer;
        try {
            const zmq = zmqAdapter.loadZeroMQ();
            Dealer = zmq.Dealer;
            console.log('Using zeromq Dealer');
        } catch (e) {
            console.log('zeromq load failed:', e.message);
            try {
                const zmq = zmqAdapter.loadRustZMQ();
                Dealer = zmq.Dealer;
                console.log('Using rust ZMQ Dealer');
            } catch (e2) {
                console.error('Both ZMQ implementations failed:', e2.message);
                process.exit(1);
            }
        }

        const routingId = 'test-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        console.log('Routing ID:', routingId);

        const socket = new Dealer({
            routingId: routingId,
        });

        socket.heartbeatInterval = 1000;
        socket.heartbeatTimeToLive = 3000;
        socket.heartbeatTimeout = 3000;

        console.log('Connecting to:', ipcAddress);
        socket.connect(ipcAddress);
        console.log('Socket connected!');

        // Set up receive loop
        let receivedAny = false;
        (async () => {
            try {
                for await (const frames of socket) {
                    receivedAny = true;
                    const message = frames.at(-1);
                    if (message) {
                        const msgStr = message.toString('utf8');
                        console.log('\nReceived:', msgStr.substring(0, 500));
                        // Try to parse as JSON
                        try {
                            const parsed = JSON.parse(msgStr);
                            console.log('Parsed:', JSON.stringify(parsed, null, 2).substring(0, 1000));
                        } catch {}
                    }
                }
            } catch (e) {
                console.error('Receive loop error:', e.message);
            }
        })();

        // Wait for connection to establish
        await new Promise(resolve => setTimeout(resolve, 2000));

        // Try sending a simple JSON-RPC healthcheck
        const reqId = 'req-' + Date.now();
        const packet = {
            version: 1,
            id: '',
            packet_type: 'user',
            payload: JSON.stringify({
                jsonrpc: '2.0',
                id: reqId,
                method: 'request',
                params: {
                    packet_type: 'request',
                    session_id: '',
                    channel_id: reqId,
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
            })
        };

        console.log('\nSending packet:', JSON.stringify(packet).substring(0, 300));
        socket.send([JSON.stringify(packet)]);

        // Wait for response
        await new Promise(resolve => setTimeout(resolve, 5000));

        if (!receivedAny) {
            console.log('\nNo response received. The ai-agent may not be listening on this address.');
            console.log('Trying to list named pipes...');

            // On Windows, ZMQ ipc:// uses named pipes
            // Let's check what named pipes exist that might be the ai-agent
            const { execSync } = require('child_process');
            try {
                const pipes = execSync('powershell -Command "[System.IO.Directory]::GetFiles(\'\\\\.\\pipe\\\') | Where-Object { $_ -match \'ai-agent|aha\' }"').toString();
                console.log('Matching pipes:', pipes);
            } catch (e) {
                console.log('Could not list pipes:', e.message);
            }
        }

        // Cleanup
        console.log('\nDisconnecting...');
        socket.disconnect(ipcAddress);
        socket.close();

        // Remove marker file
        try { fs.unlinkSync(markerPath); } catch {}

    } catch (e) {
        console.error('Error:', e.message);
        console.error(e.stack);
    }

    process.exit(0);
}

main();

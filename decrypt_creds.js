// decrypt_creds.js - 解密 ncm-cli credentials.enc.json
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const credPath = path.join(process.env.HOME || process.env.USERPROFILE, '.config', 'ncm-cli', 'credentials.enc.json');

if (!fs.existsSync(credPath)) {
    console.error('Credentials file not found:', credPath);
    process.exit(1);
}

const enc = JSON.parse(fs.readFileSync(credPath, 'utf-8'));
const iv = Buffer.from(enc.iv, 'hex');
const encrypted = Buffer.from(enc.data, 'base64');

// 使用 DPAPI 解密（通过 Windows API）
// ncm-cli 使用 CryptoJS AES + DPAPI 保护的密钥
// 但 Windows 上 CryptoJS 的默认 key derivation 可能不同

// 尝试用已知的 ncm-cli 密钥解密（常见默认值）
// 或者直接用 Node.js 的 crypto + DPAPI

// 实际上，ncm-cli 使用 node-dpapi 包来调用 Windows DPAPI
// 让我们检查 ncm-cli 的加密代码

console.log('IV:', enc.iv);
console.log('Encrypted length:', enc.data.length);
console.log('Encrypted (first 100 chars):', enc.data.substring(0, 100));

// 尝试解密 - 使用 ncm-cli 的方式
// ncm-cli 的 CryptoJS.aes.encrypt 使用 'password' 模式
// 密钥由 DPAPI 保护

// 试试用空密码和默认参数
try {
    // 这个方法不会work，但我们先看看数据格式
    const test = crypto.createDecipheriv('aes-256-cbc', Buffer.alloc(32), iv);
    const out = test.update(encrypted);
    console.log('AES test (no key):', out.toString('utf-8').substring(0, 100));
} catch(e) {
    console.log('AES test failed:', e.message);
}

// 检查加密数据是否是 JSON 格式
const rawBuf = Buffer.from(enc.data, 'base64');
console.log('First 4 bytes (hex):', rawBuf.slice(0, 4).toString('hex'));
console.log('Data length:', rawBuf.length);

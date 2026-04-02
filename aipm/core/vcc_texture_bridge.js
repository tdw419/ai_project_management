/**
 * VCC Texture Bridge - Reads colony state from /dev/shm/vcc_colony.rgba
 * Zero-copy shared memory reading for GlyphLang GPU VM visualization.
 */
const fs = require('fs');
const path = require('path');

const VCC_SHM_PATH = '/dev/shm/vcc_colony.rgba';
const VCC_SIZE = 256;
const VCC_SIZE_BYTES = VCC_SIZE * VCC_SIZE * 4;

class VCCTextureBridge {
  constructor(options = {}) {
    this.pollInterval = options.pollInterval || 100;
    this.onFrame = options.onFrame || (() => {});
    this.fd = null;
    this.timer = null;
    this.lastStat = null;
  }

  start() {
    if (this.timer) return;
    this.poll();
    this.timer = setInterval(() => this.poll(), this.pollInterval);
  }

  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this.closeFile();
  }

  openFile() {
    try {
      this.fd = fs.openSync(VCC_SHM_PATH, 'r');
      return true;
    } catch (e) {
      return false;
    }
  }

  closeFile() {
    if (this.fd !== null) {
      try { fs.closeSync(this.fd); } catch (e) {}
      this.fd = null;
    }
  }

  readFrame() {
    if (this.fd === null) {
      if (!this.openFile()) return null;
    }

    try {
      const buf = Buffer.alloc(VCC_SIZE_BYTES);
      const bytesRead = fs.readSync(this.fd, buf, 0, VCC_SIZE_BYTES, 0);
      if (bytesRead !== VCC_SIZE_BYTES) {
        this.closeFile();
        return null;
      }
      return buf;
    } catch (e) {
      this.closeFile();
      return null;
    }
  }

  computeStats(rgbaBuffer) {
    if (!rgbaBuffer) return null;

    let activeVMs = 0;
    let totalBrightness = 0;

    for (let i = 0; i < VCC_SIZE * VCC_SIZE; i++) {
      const offset = i * 4;
      const r = rgbaBuffer[offset];
      const g = rgbaBuffer[offset + 1];
      const b = rgbaBuffer[offset + 2];
      const a = rgbaBuffer[offset + 3];

      if (a > 0 && (r > 0 || g > 0 || b > 0)) {
        activeVMs++;
        totalBrightness += (r + g + b) / 3;
      }
    }

    const fillPct = (activeVMs / (VCC_SIZE * VCC_SIZE)) * 100;
    const avgBrightness = activeVMs > 0 ? totalBrightness / activeVMs : 0;

    return {
      activeVMs,
      fillPct: Math.round(fillPct * 100) / 100,
      avgBrightness: Math.round(avgBrightness * 100) / 100,
      timestamp: Date.now()
    };
  }

  poll() {
    const frame = this.readFrame();
    const stats = this.computeStats(frame);

    if (stats && (stats.activeVMs !== this.lastStat?.activeVMs || stats.fillPct !== this.lastStat?.fillPct)) {
      this.lastStat = stats;
      this.onFrame({ frame, stats });
    }
  }

  downsample(w, h) {
    const frame = this.readFrame();
    if (!frame) return null;

    const result = Buffer.alloc(w * h * 4);
    const xScale = VCC_SIZE / w;
    const yScale = VCC_SIZE / h;

    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const srcX = Math.floor(x * xScale);
        const srcY = Math.floor(y * yScale);
        const srcOffset = (srcY * VCC_SIZE + srcX) * 4;
        const dstOffset = (y * w + x) * 4;
        result[dstOffset] = frame[srcOffset];
        result[dstOffset + 1] = frame[srcOffset + 1];
        result[dstOffset + 2] = frame[srcOffset + 2];
        result[dstOffset + 3] = frame[srcOffset + 3];
      }
    }
    return result;
  }

  toASCII(cols, rows) {
    const frame = this.readFrame();
    if (!frame) return '';

    const CHARS = ' .:-=+*#%@';
    const xScale = VCC_SIZE / cols;
    const yScale = VCC_SIZE / rows;
    let result = '';

    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        const srcX = Math.floor(x * xScale);
        const srcY = Math.floor(y * yScale);
        const offset = (srcY * VCC_SIZE + srcX) * 4;
        const brightness = (frame[offset] + frame[offset + 1] + frame[offset + 2]) / 3;
        const charIdx = Math.floor((brightness / 255) * (CHARS.length - 1));
        result += CHARS[charIdx];
      }
      result += '\n';
    }
    return result;
  }

  getRawRGBA() {
    return this.readFrame();
  }

  getLatestStats() {
    return this.lastStat;
  }
}

module.exports = { VCCTextureBridge, VCC_SIZE, VCC_SHM_PATH };
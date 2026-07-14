// 依赖-free 的最小 ZIP 打包器（STORE 存储，不压缩）。
// 用于在浏览器端把导出的代码文件与 requirements.txt 打包成 .zip 下载，
// 无需引入第三方库，也无需改动/重装本机 Agent。

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) {
    crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

export interface ZipEntry {
  name: string;
  content: string;
  // Unix 文件权限（八进制），默认 0o644；可执行脚本传 0o755
  mode?: number;
}

// 固定的 DOS 时间戳（1980-01-01 00:00:00），保证输出确定、且不早于 ZIP 允许的最小日期
const DOS_TIME = 0;
const DOS_DATE = 0x0021;
// “制作版本”：高字节 3 = Unix 主机（使外部属性中的权限位生效），低字节 20 = ZIP 2.0
const VERSION_MADE_BY = (3 << 8) | 20;
const DEFAULT_MODE = 0o644;

export function createZip(entries: ZipEntry[]): Uint8Array {
  const encoder = new TextEncoder();
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;

  for (const entry of entries) {
    const nameBytes = encoder.encode(entry.name);
    const data = encoder.encode(entry.content);
    const crc = crc32(data);
    const size = data.length;

    const local = new Uint8Array(30 + nameBytes.length);
    const lv = new DataView(local.buffer);
    lv.setUint32(0, 0x04034b50, true);        // 本地文件头签名
    lv.setUint16(4, 20, true);                // 解压所需版本
    lv.setUint16(6, 0x0800, true);            // 通用标志位：文件名/内容为 UTF-8
    lv.setUint16(8, 0, true);                 // 压缩方式：0 = 存储
    lv.setUint16(10, DOS_TIME, true);
    lv.setUint16(12, DOS_DATE, true);
    lv.setUint32(14, crc, true);
    lv.setUint32(18, size, true);             // 压缩后大小（存储时等于原始大小）
    lv.setUint32(22, size, true);             // 原始大小
    lv.setUint16(26, nameBytes.length, true); // 文件名长度
    lv.setUint16(28, 0, true);                // 扩展字段长度
    local.set(nameBytes, 30);
    localParts.push(local, data);

    const mode = entry.mode ?? DEFAULT_MODE;
    const externalAttrs = ((0o100000 | mode) << 16) >>> 0; // 高 16 位 = Unix st_mode（普通文件）
    const central = new Uint8Array(46 + nameBytes.length);
    const cv = new DataView(central.buffer);
    cv.setUint32(0, 0x02014b50, true);        // 中央目录记录签名
    cv.setUint16(4, VERSION_MADE_BY, true);   // 制作版本（Unix 主机）
    cv.setUint16(6, 20, true);                // 解压所需版本
    cv.setUint16(8, 0x0800, true);            // 标志位：UTF-8
    cv.setUint16(10, 0, true);                // 压缩方式
    cv.setUint16(12, DOS_TIME, true);
    cv.setUint16(14, DOS_DATE, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, size, true);
    cv.setUint32(24, size, true);
    cv.setUint16(28, nameBytes.length, true);
    cv.setUint16(30, 0, true);                // 扩展字段长度
    cv.setUint16(32, 0, true);                // 注释长度
    cv.setUint16(34, 0, true);                // 起始磁盘号
    cv.setUint16(36, 0, true);                // 内部属性
    cv.setUint32(38, externalAttrs, true);    // 外部属性（含 Unix 权限）
    cv.setUint32(42, offset, true);           // 本地文件头偏移
    central.set(nameBytes, 46);
    centralParts.push(central);

    offset += local.length + data.length;
  }

  const centralSize = centralParts.reduce((sum, part) => sum + part.length, 0);
  const centralOffset = offset;

  const end = new Uint8Array(22);
  const ev = new DataView(end.buffer);
  ev.setUint32(0, 0x06054b50, true);          // 中央目录结束记录签名
  ev.setUint16(4, 0, true);                   // 当前磁盘号
  ev.setUint16(6, 0, true);                   // 中央目录起始磁盘号
  ev.setUint16(8, entries.length, true);      // 本磁盘记录数
  ev.setUint16(10, entries.length, true);     // 总记录数
  ev.setUint32(12, centralSize, true);        // 中央目录大小
  ev.setUint32(16, centralOffset, true);      // 中央目录偏移
  ev.setUint16(20, 0, true);                  // 注释长度

  const total = centralOffset + centralSize + end.length;
  const out = new Uint8Array(total);
  let pos = 0;
  for (const part of localParts) {
    out.set(part, pos);
    pos += part.length;
  }
  for (const part of centralParts) {
    out.set(part, pos);
    pos += part.length;
  }
  out.set(end, pos);
  return out;
}

export function scalarNpy(descr: string, data: Buffer, shape = '(1, 1, 1)', order = 'False'): Buffer {
  const text = `{'descr': '${descr}', 'fortran_order': ${order}, 'shape': ${shape}, }`;
  const padding = (64 - (10 + text.length + 1) % 64) % 64;
  const header = Buffer.from(text + ' '.repeat(padding) + '\n', 'ascii');
  const prefix = Buffer.from([0x93, 0x4e, 0x55, 0x4d, 0x50, 0x59, 1, 0, 0, 0]);
  prefix.writeUInt16LE(header.length, 8);
  return Buffer.concat([prefix, header, data]);
}

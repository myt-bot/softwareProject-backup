/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 后端云端服务地址（生产构建时注入，如 https://fk.kanzakiyui.com） */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import vue from "@astrojs/vue";

import mdx from "@astrojs/mdx";

// https://astro.build/config
export default defineConfig({
  output: "static",
  integrations: [
    starlight({
      title: "Suan Toolkit",
      // 为此网站设置中文为默认语言。
      defaultLocale: "root",
      locales: {
        // 简体中文文档在 `src/content/docs/zh-cn/` 中。
        root: {
          label: "简体中文",
          lang: "zh-CN",
        },
        en: {
          // 英文文档在 `src/content/docs/en/` 中。
          label: "English",
          lang: "en", // lang 是 root 语言必须的
        },
      },
      social: {
        github: "https://github.com/withastro/starlight",
      },
      logo: {
        src: "./src/assets/logo.png",
      },
      sidebar: [
        {
          label: "开发者指南",
          translations: {
            en: "Developer Guide",
          },
          items: [
            // Each item here is one entry in the navigation menu.
            {
              label: "Apps",
              translations: {
                en: "Apps",
              },
              items: [
                {
                  label: "pyqt",
                  translations: {
                    en: "pyqt",
                  },
                  items: [
                    {
                      label: "环境配置",
                      translations: {
                        en: "Configuration",
                      },
                      link: "/dev_guide/pyqt/configuration",
                    },
                    {
                      label: "项目结构",
                      translations: {
                        en: "structure",
                      },
                      link: "/dev_guide/pyqt/structure",
                    },
                  ],
                },
              ],
            },
          ],
        },
        {
          label: "用户指南",
          translations: {
            en: "User Guide",
          },
          items: [
            // Each item here is one entry in the navigation menu.
            {
              label: "概述",
              translations: {
                en: "index",
              },
              link: "/user_guide/",
            },
          ],
        },
      ],
    }),
    vue(),
    mdx(),
  ],
});

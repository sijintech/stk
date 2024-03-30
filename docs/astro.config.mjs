import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import vue from "@astrojs/vue";

import mdx from "@astrojs/mdx";

// https://astro.build/config
export default defineConfig({
  output:'static',
  integrations: [starlight({
    title: 'stk',
    // 为此网站设置英语为默认语言。
    defaultLocale: 'root',
    locales: {
      // 英文文档在 `src/content/docs/en/` 中。
      root: {
        label: 'English',
        lang: 'en', // lang 是 root 语言必须的
      },
      // 简体中文文档在 `src/content/docs/zh-cn/` 中。
      'zh-cn': {
        label: '简体中文',
        lang: 'zh-CN',
      },
    },
    social: {
      github: 'https://github.com/withastro/starlight'
    },
    logo: {
      src: './src/assets/logo.png'
    },
    sidebar: [{
      label: 'Developer Guide',
      translations: {
        'zh-CN': '开发者指南',
      },
      items: [
        // Each item here is one entry in the navigation menu.
        {
          label: 'index',
          translations: {
            'zh-CN': '概述',
          },
          link: '/dev_guide/'
        },
      
      ]
    }, 
    {
      label: 'User Guide',
      translations: {
        'zh-CN': '用户指南',
      },
      items: [
        // Each item here is one entry in the navigation menu.
        {
          label: 'index',
          translations: {
            'zh-CN': '概述',
          },
          link: '/user_guide/'
        },
      
      ]
    }, 
  ]
  }), vue(), mdx()]
});
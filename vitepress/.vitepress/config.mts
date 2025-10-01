import { defineConfig } from 'vitepress'
import { fileURLToPath } from 'node:url'

export default defineConfig({

  outDir: fileURLToPath(new URL ('../../docs', import.meta.url)),
  title: 'ormysql',
  description: 'Async ORM for MariaDB/MySQL',
  base: '/mysql-orm-lite/',
  lang: 'ru-RU',
  lastUpdated: true,
  cleanUrls: true,

  themeConfig: {
    nav: [
      { text: 'Guide', link: '/guide/get-started' },
      { text: 'Install', link: 'https://pypi.org/project/ormysql/' }
    ],
        sidebar: [
      {
        text: 'Guide',
        items: [
          { text: 'Getting Started', link: '/guide/get-started' },
          { text: 'DB', link: '/guide/db' },
          { text: 'Migrations', link: '/guide/migrations' },
          { text: 'Fields', link: '/guide/fields' },
          { text: 'Queries', link: '/guide/queries' },
          { text: 'Advanced Queries', link: '/guide/advanced-queries' },
          { text: 'Relations', link: '/guide/relations' },
          { text: 'Session', link: '/guide/session' },
          { text: 'Transaction', link: '/guide/transaction' },
          { text: 'API Reference', link: '/guide/reference' }
        ]
      }
    ],
    socialLinks: [{ icon: 'github', link: 'https://github.com/VsevolodKrasovskyi/mysql-orm-lite' }],
    outline: [2,3],
    footer: {
      message: 'MIT',
      copyright: '© ' + new Date().getFullYear() + ' ormysql'
    }
  },
})


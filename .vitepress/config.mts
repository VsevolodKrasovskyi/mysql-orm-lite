import { defineConfig } from 'vitepress'

export default defineConfig({

  title: 'Ormysql',
  description: 'Async ORM for MariaDB/MySQL',
  base: '/ormysql/',
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
    socialLinks: [{ icon: 'github', link: 'https://github.com/ormysql/ormysql' }],
    outline: [2,3],
    footer: {
      message: 'MIT',
      copyright: '© ' + new Date().getFullYear() + ' ormysql'
    }
  },
})


const themeOptions = require('gatsby-theme-mupro-doc/theme-options');

const navConfig = {
    // 'MUPRO Dielectric Breakdown': {
    //     url: 'https://mupro-dielectricbreakdown.surge.sh',
    //     description: 'Learn how to use the dielectric breakdown module.'
    // },
    // 'MUPRO Simple Visualization': {
    //     url: 'https://mupro-visualization.surge.sh/',
    //     description: 'Learn how to use the simple visualization program provide by us.'
    // },
  };
  
  const footerNavConfig = {
    MUPRO: {
        href: 'https://mupro.co/',
        target: '_blank',
        rel: 'noopener noreferrer'
    },
    Contribute: {
    href: 'https://nibiru.llc'
    }
  };
  
  themes = {
    siteName: 'Nibiru Math FFT collection',
    pageTitle: 'Nibiru Math FFT collection',
    menuTitle: 'Nibiru',
    gaTrackingId: '',
    algoliaApiKey: 'e9a5d57305100ea65a89364133fccb3a',
    algoliaIndexName: 'muprodoc',
    baseUrl: 'https://nibiru-math-fft.surge.sh/',
    twitterHandle: '',
    spectrumHandle: '',
    youtubeUrl: '',
    logoLink: 'https://nibiru-math-fft.surge.sh/',
    baseDir: '',
    navConfig,
    footerNavConfig   
  };
  

module.exports = {
    pathPrefix:'/',
    plugins:[
        {
            resolve:'gatsby-theme-mupro-doc',
            options:{
                ...themeOptions,
                ...themes,
                root: __dirname,
                subtitle: 'Nibiru FFT solver collections',
                description: 'The Nibiru FFT solver collection',
                sidebarCategories:{
                    null:['index'],
                    Installation: [
                        'installation/installation',
                    ],
                    Documentation: [
                        'documentations/introduction',
                        'documentations/programming',
                        'documentations/Poisson',
                        'documentations/Elastic',
                        'documentations/quick-tutorial',
                    ],
                    Examples: [
                        'examples/exmaple1',
                    ],
                    Resources: [
                        'resources/faq',
                        'resources/publications',
                        'resources/references',
                    ],
                }
            }
        }
    ]
}
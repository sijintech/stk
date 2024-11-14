import { defineConfig } from 'vitepress'
import markdownItKatex from 'markdown-it-katex'
import markdownItFootnote from 'markdown-it-footnote'

const customElements = [
    'math',
    'maction',
    'maligngroup',
    'malignmark',
    'menclose',
    'merror',
    'mfenced',
    'mfrac',
    'mi',
    'mlongdiv',
    'mmultiscripts',
    'mn',
    'mo',
    'mover',
    'mpadded',
    'mphantom',
    'mroot',
    'mrow',
    'ms',
    'mscarries',
    'mscarry',
    'mscarries',
    'msgroup',
    'mstack',
    'mlongdiv',
    'msline',
    'mstack',
    'mspace',
    'msqrt',
    'msrow',
    'mstack',
    'mstack',
    'mstyle',
    'msub',
    'msup',
    'msubsup',
    'mtable',
    'mtd',
    'mtext',
    'mtr',
    'munder',
    'munderover',
    'semantics',
    'math',
    'mi',
    'mn',
    'mo',
    'ms',
    'mspace',
    'mtext',
    'menclose',
    'merror',
    'mfenced',
    'mfrac',
    'mpadded',
    'mphantom',
    'mroot',
    'mrow',
    'msqrt',
    'mstyle',
    'mmultiscripts',
    'mover',
    'mprescripts',
    'msub',
    'msubsup',
    'msup',
    'munder',
    'munderover',
    'none',
    'maligngroup',
    'malignmark',
    'mtable',
    'mtd',
    'mtr',
    'mlongdiv',
    'mscarries',
    'mscarry',
    'msgroup',
    'msline',
    'msrow',
    'mstack',
    'maction',
    'semantics',
    'annotation',
    'annotation-xml'
]

export default defineConfig({
    title: "Effective Properties",
    description: 'The user manual for MuPRO Effective Properties Desktop version',
    lastUpdated: true,
    markdown: {
        lineNumbers: true,
        config: (md) => {
            md.use(markdownItKatex),
                md.use(markdownItFootnote)
        }
    },
    vue: {
        template: {
            compilerOptions: {
                isCustomElement: (tag) => customElements.includes(tag)
            }
        }
    },
    themeConfig: {
        algolia: {
            appId: 'RTVIBZAZR5',
            apiKey: '91b2bf0aed1a2be40676a71666c2af68',
            indexName: 'effective-properties-desktop'
        },
        footer: {
            message: 'This website is developed using vitepress.',
            copyright: 'By MuPRO LLC, 2020-present'
        },
        nav: [
            { text: "MuPRO", link: 'https://mupro.co' },
            { text: "User Manual", link: '/manual/introduction' },
            { text: "Usage Examples", link: '/examples/overview' },
        ],
        sidebar: {
            '/manual/': getManual(),
            '/examples/': getExamples()
        }
    }
})

function getManual() {
    return [{
        text: 'Overview',
        collapsible: true,
        items: [
            { text: 'Introduction', link: '/manual/introduction' },
            { text: 'Get Started', link: '/manual/license_index' },
            { text: 'FAQs', link: '/manual/faq' },
            { text: 'References', link: '/manual/ref' }
        ]
    },
    {
        text: 'Graphical interface',
        collapsible: true,
        items: [
            { text: "Overview", link: '/manual/gui_overview' },
            { text: "Menu", link: '/manual/gui_menu' },
            { text: "Input", link: '/manual/gui_input' },
            { text: "Output", link: '/manual/gui_output' },
        ]
    },
    {
        text: 'Files',
        collapsible: true,
        items: [
            { text: "Input File", link: '/manual/input_file_xml' },
            { text: "Structure File", link: '/manual/input_file_structure' },
            { text: "Output Files", link: '/manual/output_files' },
        ]
    },
    {
        text: 'Material',
        collapsible: true,
        items: [
            { text: "Material", link: '/manual/material' },
            { text: "Properties", link: '/manual/material_properties' },
        ]
    },
    {
        text: 'Geometries',
        collapsible: true,
        items: [
            { text: "Overview", link: '/manual/structure_generator_overview' },
            { text: "Slab", link: '/manual/structure_generator_slab' },
            { text: "Ellipsoid", link: '/manual/structure_generator_ellipsoid' },
            { text: "Random Ellipsoid", link: '/manual/structure_generator_random_ellipsoid' },
            { text: "Random Scale Ellipsoid", link: '/manual/structure_generator_random_scale_ellipsoid' },
            { text: "Ellipsoid Shell", link: '/manual/structure_generator_ellipsoid_shell' },
            { text: "Random ellipsoid Shell", link: '/manual/structure_generator_random_ellipsoid_shell' },
            { text: "Random Scale Ellipsoid Shell", link: '/manual/structure_generator_random_scale_ellipsoid_shell' }
        ]
    }, {
        text: 'Systems',
        collapsible: true,
        items: [
            { text: "Overview", link: '/manual/systems' },
            { text: "Dielectric", link: '/manual/dielectric' },
            { text: "Electrical", link: '/manual/electrical' },
            { text: "Magnetic", link: '/manual/magnetic' },
            { text: "Diffusion", link: '/manual/diffusion' },
            { text: "Thermal", link: '/manual/thermal' },
            { text: "Elastic", link: '/manual/elastic' },
            { text: "Piezoelectric", link: '/manual/piezoelectric' },
            { text: "Piezomagnetic", link: '/manual/piezomagnetic' }
        ]
    }]
}

function getExamples() {
    return [
        {
            text: 'Overview',
            collapsible: false,
            items: [
                { text: 'Overview', link: '/examples/overview' },
            ]
        },
        {
            text: 'Dielectric',
            collapsible: true,
            items: [
                { text: 'Random ellispoid', link: '/examples/dielectric_random_ellipsoid' },
            ]
        },
        {
            text: 'Elastic',
            collapsible: true,
            items: [
                { text: 'Custom microstructure', link: '/examples/elastic_custom_microstructure' },
            ]
        },
        {
            text: 'Thermal',
            collapsible: true,
            items: [
                { text: 'Three phases', link: '/examples/thermal_three_phases' }
            ]
        },
        {
            text: 'Diffusion',
            collapsible: true,
            items: [
                { text: 'Ellipsoid Shell', link: '/examples/diffusion_ellipsoid_shell' }
            ]
        }
    ]
}

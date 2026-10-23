// http://js.cytoscape.org/#cy.style
//TODO: try cy.batch()  http://js.cytoscape.org/#cy.batch

cy.style()
        .selector('node')
        .style({
            'color': '#c8c8c8',
            'background-opacity': 1,
            'background-color': '#32383e',
        })
        .selector('node.link')
        .style({
            'color': '#609dd2',
            'border-color': '#609dd2',
            'background-opacity': 1,
        })
        .selector('node.link_hover')
        .style({
            'background-opacity': 1,
            'background-color': '#3e444c',
            'color': '#88b5dd',
            'border-color': '#88b5dd',
        })
        .selector('node.campaign')
        .style({
            'background-opacity': 0,
            'border-color': '#5A5A5A',
        })
        // The progress colours from maps.js (#2678), lightened for the dark background the
        // same way the link blue above is (#2f70a8 -> #609dd2): the light-theme green and
        // yellow are mixed for a white page and go muddy against #32383e.
        .selector('node.approved')
        .style({
            'border-color': '#77c977',
        })
        .selector('node.awaiting-approval')
        .style({
            'border-color': '#f5c26b',
        })
        .update()
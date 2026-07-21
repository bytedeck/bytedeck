// REF:  http://js.cytoscape.org/#core
//
// Assumes cy variables has already been loaded.


/***************************************
 * STYLE OPTIONS
 * https://js.cytoscape.org/#cy.style
 *
/**************************************/

cy.style()
    .selector('node')
      .style({
        "label": "data(label)",
        "text-valign": "center",
        "text-halign": "right",
        "text-margin-x": -150,
        "text-wrap": "wrap",
        "text-max-width": 147,
        "background-position-x": 0,
        "height": 24,
        "font-size": 12,
        "background-fit": "contain",
        "shape": "roundrectangle",
        "background-opacity": 0,
        "width": 180,
        "border-width": 1,
        "padding-right": 5,
        "padding-left": 5,
        "padding-top": 5,
        "padding-bottom": 5,
        "text-events": "yes",
        "background": "data(background)",
      })
    .selector("edge")
      .style({
        "width": 1,
        "curve-style": "bezier",
        // "curve-style": "taxi",
        "taxi-direction": "vertical",
        "taxi-turn": "15px",
        "taxi-turn-min-distance": "15px",
        "line-color": "black",
        "line-style": "solid",
        "target-arrow-shape": "triangle-backcurve",
        "target-arrow-color": "black",
      })
    .selector("edge[label]") // add labels to edges that have them.
      .style({
        "text-rotation": "0deg",
        "label": "data(label)",
        "text-halign": "right",
        // "text-max-width": 130,
        // "text-min-width": 130,
      })
    .selector("$node > node") // compound nodes (campaigns)
      .style({
        "text-rotation": "-90deg",
        "text-halign": "left",
        "text-margin-x": -10,
        "text-margin-y": -40,
        // Campaign labels run vertically along the node's edge, so the generic node
        // `text-max-width` wraps long names onto stacked lines (see issue #1289).
        // Disable wrapping here to keep each campaign name on a single line.
        "text-wrap": "none"
      })
    .selector('edge.repeat-edge')
      .style({
        'loop-direction': '100deg',
        'loop-sweep': '-20deg',
        'target-endpoint': '90deg',
        'source-endpoint': '103deg',
        'control-point-step-size': 80,
        'text-margin-x': 10,
        'text-margin-y': -3,
        'font-size': 12,
      })
    .selector('edge.complicated-prereqs')
      .style({
        "line-style": "dashed",
      })
    .selector(".link_hover")
      .style({
        "background-opacity": 1,
        "background-color": "#e5e5e5"
      })
    .selector(".link")
      .style({
        "color": "#2f70a8",
        "border-color": "#2f70a8"
      })
    .selector (".Badge")
      .style({
        "border-width": 3,
        "shape": "cut-rectangle",
      })
    .selector(".hidden")
      .style({
        "opacity": 0
      })
    .selector('node.parent-map, node.child-map')
      .style({
        "label": "data(label)",
        // "text-halign": "center",
        // "text-margin-x": 0,
        "border-style": 'dashed',
      })
    .selector('node.parent-map')
      .style({
        "text-halign": "center",
        "text-margin-x": 0,
      })
    .update()
;


/***************************************
 * LAYOUT OPTIONS
 * https://js.cytoscape.org/#core/layout
 *
/**************************************/

// #1787: Keep a campaign's quests vertically stacked even when one of them is also a
// prerequisite for a quest OUTSIDE the campaign.
//
// dagre positions each node horizontally (Brandes-Köpf) by aligning it under the
// *median* of its neighbours, and it ignores edge weight when doing so. So a quest that
// is a prereq for both its in-campaign successor and an out-of-campaign quest gets
// centred between the two, dragging the in-campaign successor sideways instead of
// keeping it directly below.
//
// dagre counts each parallel edge as a separate neighbour (its graph is a multigraph),
// so temporarily adding a hidden duplicate of every intra-campaign edge — one whose
// source and target share the same compound/campaign parent — pulls the median back
// onto the in-campaign successor. The chain stacks vertically and the out-of-campaign
// branch is pushed off to the side. When a quest branches to two quests that are BOTH
// in the campaign, both edges are duplicated equally, so they still spread apart as
// before (matching the issue's "unless both subsequent quests are within the same
// campaign"). The duplicates only bias the layout; they're removed right after
// positioning (dagre runs synchronously here since animation is off), so they never
// render or affect interaction.
var campaignLayoutEdges = [];
cy.edges().forEach(function (edge) {
    var sourceParent = edge.source().parent();
    // nonempty() guards the top-level case: two parent-less nodes both have an empty
    // parent collection, and empty.same(empty) is true, which would wrongly match
    // every edge between quests that aren't in any campaign.
    if (sourceParent.nonempty() && sourceParent.same(edge.target().parent())) {
        campaignLayoutEdges.push({
            group: 'edges',
            data: { source: edge.source().id(), target: edge.target().id() },
            classes: 'hidden',
        });
    }
});
var addedCampaignLayoutEdges = cy.add(campaignLayoutEdges);

var layout = cy.layout({

    // name: 'breadthfirst',
    // directed: true,
    // grid: false,
    // spacingFactor: 0.5,
    // maximal: true,

    // animate: true,
    fit: false,  // whether to fit to viewport

    "name": "dagre",
    "nodeSep": 45,  // horizontal seperation of campaigns/chains/columns
    "rankSep": 15,  // vertical seperation of nodes // try 24 for taxi?
});
layout.run()

// Remove the layout-only helper edges now that every node has its position.
addedCampaignLayoutEdges.remove();

/***************************************
 *
 * BEHAVIOUR/INTERACTIVE OPTIONS
 *
/**************************************/

// redirect to link
cy.on('tap', '[href]', function(){
    window.location.href = this.data('href');
});

cy.on('mouseover', '[href]', function(){
    $('#cy').css('cursor', 'pointer');
    this.addClass('link_hover');
});
cy.on('mouseout', '[href]', function(){
    $('#cy').css('cursor', 'move');
    this.removeClass('link_hover');
});

// nodes that don't link
cy.on('mouseover', '[^href]', function(){
    $('#cy').css('cursor', 'default');
});
cy.on('mouseout', '[^href]', function(){
    $('#cy').css('cursor', 'move');
});


$(document).ready(function() {

    cy.ready( function () {
      updateBounds();
    });

    //if they resize the window, resize the diagram
    $(window).resize(function () {
        console.log("resize")
        updateBounds();
    });

}); // dom ready


var updateBounds = function () {
    cy.reset()
    var bounds = cy.elements().boundingBox();
    $('#cy').css('height', bounds.h + 100);
    cy.zoom(1.0)
    cy.resize();
    cy.center();
    updateZooming()
};

var updateZooming = function () {
    // enable zooming if mobile device or smallscreen (otherwise zooming is annoying and
    // messes up page scrolling when using mouse wheel)
    var small_screen = window.matchMedia("(max-width: 767px)")
    cy.userZoomingEnabled(small_screen.matches);
}

$("#btn-fullscreen").click(function() {
    $("#cy").toggleClass("fullscreen");
    $("#fullscreen").toggleClass("fullscreen-toggle");
})

$("#btn-print").click(function() {
    var png64 = cy.png({
        full: true
    });
    var windowContent = '<!DOCTYPE html>';
    windowContent += '<html>'
    windowContent += '<head><title>Print canvas</title></head>';
    windowContent += '<body>'
    windowContent += '<img src="' + png64 + '">';
    windowContent += '</body>';
    windowContent += '</html>';
    var printWin = window.open();
    printWin.document.open();
    printWin.document.write(windowContent);
    printWin.document.close();
    printWin.focus();
    printWin.print();
});

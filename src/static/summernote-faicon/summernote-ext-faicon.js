(function (factory) {
    /* global define */
    if (typeof define === 'function' && define.amd) {
        // AMD. Register as an anonymous module.
        define(['jquery'], factory);
    } else if (typeof module === 'object' && module.exports) {
        // Node/CommonJS
        module.exports = factory(require('jquery'));
    } else {
        // Browser globals
        factory(window.jQuery);
    }
}(function ($) {

    // fontawesome icon picker plugin
    $.extend($.summernote.plugins, {
        /**
         * @param {Object} context - context object has status of editor.
         */
        'faicon': function (context) {
            var self = this;
            var ui = $.summernote.ui;
            var options = context.options;

                        // font-awesome: version 4.7.0; removed aliases.
            // The icon list lives in static/js/fa_icons_4.7.0.js (window.faIcons) so it
            // is shared with the Rank icon-picker widget instead of duplicated here.
            var fa_icons = (window.faIcons || {});

            var addListener = function () {
                $('body').on('click', '.note-ext-faicon-search :input', function (e) {
                    e.stopPropagation();
                });
            };

            // add context menu button
            context.memo('button.faicon', function () {
                return ui.buttonGroup({
                    className: 'note-ext-faicon',
                    children: [
                        ui.button({
                            className: 'dropdown-toggle',
                            contents: '<i class="fa fa-flag"/> ' + ui.icon(options.icons.caret, 'span'),
                            tooltip: 'Icon',
                            data: {
                                toggle: 'dropdown'
                            },
                            click: function() {
                                // Cursor position must be saved because is lost when dropdown is opened.
                                context.invoke('editor.saveRange');
                            }
                        }),
                        ui.dropdown({
                            className: 'dropdown-faicon',
                            items: [
                                '<li>',
                                '<div class="btn-group">',
                                '  <div class="note-ext-faicon-search">',
                                '  <input type="text" placeholder="search..." class="form-control" />',
                                '  </div>',
                                '  <div class="note-ext-faicon-list" />',
                                '</div>',
                                '</li>'
                            ].join(''),
                            callback: function ($dropdown) {
                                self.$search = $('.note-ext-faicon-search :input', $dropdown);
                                self.$list = $('.note-ext-faicon-list', $dropdown);
                            }
                        })
                    ]
                }).render();
            });

            // This events will be attached when editor is initialized.
            this.events = {
                // This will be called after modules are initialized.
                'summernote.init': function (we, e) {
                    addListener();
                },
            };

            // You can create elements for plugin
            self.initialize = function () {
                var $search = self.$search;
                var $list = self.$list;

                // fill/activate the elements in the inline dialog.
                self.$search.keyup(function () {
                    self.filter($search.val());
                });

                // create icons by list
                $.each(fa_icons, function (icon_name, hex_code) {
                    $list.append('<button class="btn btn-default btn-sm" ' +
                        'title="' + icon_name + '" data-hexcode="' + hex_code + '">' +
                        '<i class="fa fa-fw fa-' + icon_name + '"></i>' +
                        '</button>');
                });

                $("button", $list).click(function (event) {
                    var $button = $(this);
                    event.preventDefault(); // else, editor form is submitted
                    context.invoke('faicon.insertIcon', $button.attr('title'), $button.data("hexcode"));
                });
            };


            // apply search filter on each key press in search input
            self.filter = function (filter) {
                var $icons = $('button', self.$list);
                var rx_filter;

                if (filter === '') {
                    $icons.show();
                }
                else {
                    rx_filter = new RegExp(filter);
                    $icons.each(function () {
                        var $item = $(this);

                        if (rx_filter.test($item.attr('title'))) {
                            $item.show();
                        }
                        else {
                            $item.hide();
                        }
                    });
                }
            };


            self.insertIcon = function (icon_name, hex_code) {
                var $fa = $('<span class="ext-faicon-subst fa">' + hex_code + '</span>').attr("data-icon", icon_name);

                // We restore cursor position and element is inserted in correct pos.
                context.invoke('editor.restoreRange');
                context.invoke('editor.focus');
                context.invoke('editor.insertNode', $fa[0]);
            };

        }
    });

}));

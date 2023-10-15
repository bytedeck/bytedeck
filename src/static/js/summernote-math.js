(function(factory){
    if(typeof define==='function'&&define.amd){
        define(['jquery'],factory);
    }else if(typeof module==='object'&&module.exports){
        module.exports=factory(require('jquery'));
    }else{
        factory(window.jQuery);
    }
}(function($){
    $.extend(true,$.summernote.lang,{
        'en-US':{ /* English */
            math:{
                dialogTitle:'Insert Math',
                tooltip:'Insert Math',
                pluginTitle:'Insert math',
                ok:'Insert',
                cancel:'Cancel'
            }
        }
    });
    $.extend($.summernote.options,{
        math:{
            icon:'<b>&sum;</b>'
        }
    });
    $.extend($.summernote.plugins,{
        'math':function(context){
            var self=this;
            var ui=$.summernote.ui;
            //var $note=context.layoutInfo.note;
            var $editor=context.layoutInfo.editor;
            //var $editable=context.layoutInfo.editable;
            var options=context.options;
            var lang=options.langInfo;


            context.memo('button.math',function(){
                let button=ui.button({
                    contents:options.math.icon,
                    tooltip:lang.math.tooltip,
                    click:function(e){
                        // Cursor position must be saved because is lost when popup is opened.
                        context.invoke('editor.saveRange');
                        context.invoke('math.show');
                    }
                });
                return button.render();
            });

            self.initialize = function(){
                let $container=options.dialogsInBody?$(document.body):$editor;
                let body=`<div class="form-group">

                    <p>Type <a href="https://khan.github.io/KaTeX/function-support.html" target=_blank">LaTeX markup</a> here: </p>
                    <p><input id="note-latex" class="form-control"></p>
                    <p>Preview: </p>
                    <div style="min-height:20px;"><span class="note-math-dialog"></span></div>

                    <script>
                    let $mathElement = $('.note-math-dialog');
                    let mathSpan = $mathElement[0];
                    let latexSpan = document.getElementById('note-latex');


                    latexSpan.addEventListener('keyup', renderMath);

                    function renderMath(){
                        let oldMath = mathSpan.innerHTML;

                        try {
                            katex.render(this.value, mathSpan);
                        }
                        catch(e) {
                            // KaTeX parse error while typing, to prevent rendered math from dissappearing while typing
                            // partially complete markup
                            mathSpan.innerHTML = oldMath;
                        }
                    }

                    </script>

                    </div>`;
                self.$dialog=ui.dialog({
                    title:lang.math.dialogTitle,
                    body:body,
                    footer:'<button class="btn btn-primary note-math-btn">'+lang.math.ok+'</button>'
                }).render().appendTo($container);
            };



            self.destroy = function(){
                ui.hideDialog(this.$dialog);
                self.$dialog.remove();
            };

            self.bindEnterKey = function($input,$btn){
                $input.on('keypress',function(event){
                    if(event.keyCode===13)$btn.trigger('click');
                });
            };

            self.bindLabels = function(){
                self.$dialog.find('.form-control:first').focus().select();
                self.$dialog.find('label').on('click',function(){
                    $(this).parent().find('.form-control:first').focus();
                });
            };

            self.show = function(){

                let $mathSpan = self.$dialog.find('.note-math-dialog');
                let $latexSpan = self.$dialog.find('#note-latex');

                let $selectedMathNode = self.getSelectedMath();

                if ($selectedMathNode === null) {
                    // reset the dialog input and math
                    $mathSpan.empty();
                    $latexSpan.val('');
                }
                else { // edit the selected math node
                    // get the hidden LaTeX markup from the selected math node
                    let hiddenLatex = $selectedMathNode.find('.note-latex').text();
                    $latexSpan.val(hiddenLatex);
                    katex.render(hiddenLatex, $mathSpan[0]);
                }

                let mathInfo = {}; // not used

                self.showMathDialog(mathInfo).then(function(mathInfo){
                    ui.hideDialog(self.$dialog);
                    let $mathNodeClone = $mathSpan.clone();
                    let $latexNode = $('<span>');
                    $latexNode.addClass('note-latex')
                        .css('display', 'none')
                        .text($latexSpan.val())
                        .appendTo($mathNodeClone);

                    // So we don't pick up the dialog node when selecting math nodes in the editor
                    $mathNodeClone.removeClass('note-math-dialog').addClass('note-math');

                    // We restore cursor position and element is inserted in correct pos.
                    context.invoke('editor.restoreRange');
                    context.invoke('editor.focus');

                    if ($selectedMathNode === null)
                        context.invoke('editor.insertNode',$mathNodeClone[0]);
                    else {// if we are editing an existing mathNode, just replace the contents:
                        if( $.trim($latexNode.html())=='') { // unless there's nothing there, then delete the node
                            $selectedMathNode.remove()
                        }
                        else {
                            $selectedMathNode.html($mathNodeClone.html());
                        }

                    }
                });
            };

            self.showMathDialog = function(editorInfo) {
                return $.Deferred(function (deferred) {
                    let $editBtn = self.$dialog.find('.note-math-btn');
                    ui.onDialogShown(self.$dialog, function () {

                        context.triggerEvent('dialog.shown');
                        $editBtn.click(function (e) {
                            e.preventDefault();
                            deferred.resolve({

                            });
                        });
                        self.bindEnterKey($editBtn);
                        self.bindLabels();
                    });
                    ui.onDialogHidden(self.$dialog, function () {
                        $editBtn.off('click');
                        if (deferred.state() === 'pending') deferred.reject();
                    });
                    ui.showDialog(self.$dialog);
                });
            };

            self.getSelectedMath = function() {
                let selection = window.getSelection();
                if( selection ){
                    // get all math nodes
                    let $selectedMathNode = null;
                    let $mathNodes = $('.note-math');
                    $mathNodes.each(function() {
                        // grab first math node in the selection (including partial).
                        if(selection.containsNode(this, true)) {
                            $selectedMathNode = $(this);
                        }
                    });
                    return $selectedMathNode;
                }

            };


        }
    });
}));

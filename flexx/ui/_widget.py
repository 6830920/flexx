"""
The base ``Widget`` class.

.. UIExample:: 100

    from flexx import app, ui

    class Example(ui.Widget):
        ''' A red widget '''
        CSS = ".flx-Example {background:#f00;}"

"""

from ..event import loop
from .. import event, app
from ..pyscript import undefined, window

from . import logger  # noqa


def create_element(type, props=None, *children):
    """ Convenience function to create a dictionary to represent
    a virtual DOM node. Intended for use inside ``Widget._render_dom()``.
    
    The content of the widget may be given as a series/list of child nodes
    (virtual or real), or a single string, which will be used as the node's
    inner HTML.
    
    The returned dictionary has three fields: type, props, children.
    """
    if len(children) == 0:
        children = None  # means, don't touch children
    elif len(children) == 1 and (isinstance(children[0], str) or
                                 isinstance(children[0], list)):
        children = children[0]
    
    return dict(type=type,
                props=props or {},
                children=children,
                )


class Widget(app.JsComponent):
    """ Base widget class.

    When *subclassing* a Widget to create a compound widget (a widget
    that acts as a container for other widgets), use the ``init()``
    method to initialize the child widgets. This method is called while
    the widget is the current widget.
    
    """

    CSS = """

    .flx-Widget {
        box-sizing: border-box;
        overflow: hidden;
        position: relative;  /* helps with absolute positioning of content */
    }
    
    /* in a notebook or otherwise embedded in classic HTML */
    .flx-container {
        min-height: 20px;
    }
    
    /* Main widget to fill the whole page */
    .flx-main-widget {
       position: absolute;
       left: 0;
       right: 0;
       width: 100%;
       top: 0;
       bottom: 0;
       height: 100%;
    }
    
    /* to position children absolute */
    .flx-abs-children > .flx-Widget {
        position: absolute;
    }
    
    /* Fix issue flexbox > Widget > layout on Chrome */
    .flx-Widget:not(.flx-Layout) > .flx-Layout {
        position: absolute;
    }
    """
    
    ## Properties
    
    container = event.StringProp('', settable=True, doc="""
        The id of the DOM element that contains this widget if
        parent is None. Use 'body' to make this widget the root.
        """)
    
    parent = event.ComponentProp(None, doc="""
        The parent widget, or None if it has no parent. Setting
        this property will update the "children" property of the
        old and new parent.
        """)
        
    children = app.LocalProperty((), doc="""
        The child widgets of this widget. This property is not settable and
        only present in JavaScript.
        """)
    
    title = event.StringProp('', settable=True, doc="""
        The string title of this widget. This is used to mark
        the widget in e.g. a tab layout or form layout, and is used
        as the app's title if this is the main widget.
        """)
    
    icon = app.LocalProperty('', settable=False, doc="""
        The icon for this widget. This is used is some widgets classes,
        and is used as the app's icon if this is the main widget.
        It is settable from Python, but only present in JavaScript.
        """)
    
    css_class = event.StringProp('', settable=True, doc="""
        The extra CSS class name to asign to the DOM element.
        Spaces can be used to delimit multiple names. Note that the
        DOM element already has a css class-name corresponding to
        its class (e.g. 'flx-Widget) and all its superclasses.
        """)
    
    flex = event.FloatPairProp((0, 0), settable=True, doc="""
        How much space this widget takes (relative to the other
        widgets) when contained in a flexible layout such as HBox,
        HFix, HSplit or FormLayout. A flex of 0 means to take
        the minimum size. Flex is a two-element tuple, but both values
        can be specified at once by specifying a scalar.
        """)
    
    size = event.FloatPairProp((0, 0), settable=False, doc="""
        The actual size of the widget. Flexx tries to keep this value
        up-to-date, but in e.g. a box layout, a change in a Button's
        text can change the size of sibling widgets.
        """)
    
    size_min_max = event.TupleProp((0, 1e9, 0, 1e9), settable=False, doc="""
        A 4-element tuple (min-width, max-width, min-height, max-height)
        derived from the element's style, in pixels.
        """)
    
    tabindex = event.IntProp(-2, settable=True, doc="""
        The index used to determine widget order when the user
        iterates through the widgets using tab. This also determines
        whether a widget is able to receive key events. Flexx automatically
        sets this property when it should emit key events.
        Effect of possible values on underlying DOM element:
        
        * -2: element cannot have focus unless its a special element like
            a link or form control (default).
        * -1: element can have focus, but is not reachable via tab.
        * 0: element can have focus, and is reachable via tab in the order
            at which the element is defined.
        * 1 and up: element can have focus, and the tab-order is determined
            by the value of tabindex.
        """)
    
    capture_mouse = event.IntProp(1, settable=True, doc="""
        To what extend the mouse is "captured".
        
        * If 0, the mouse is not captured, and move events are only emitted
          when the mouse is pressed down (not recommended).
        * If 1 (default) the mouse is captured when pressed down, so move
          and up events are received also when the mouse is outside the widget.
        * If 2, move events are also emitted when the mouse is not pressed down
          and inside the widget.
        """)
    
    @event.action
    def set_icon(self, val):
        """ Set the icon for this widget. This is used is some widgets classes,
        and is used as the app's icon if this is the main widget.
        It is settable from Python, but the property is not available in Python.
        
        Can be a url, a relative url to a shared asset, or a base64
        encoded image. In the future this may also support names in
        icon packs like FontAwesome.
        """
        if not isinstance(val, str):
            raise TypeError('Icon must be a string')
        self._mutate_icon(val)
    
    ## Methods
    
    def __init__(self, *init_args, **kwargs):

        # Handle parent
        parent = kwargs.pop('parent', None)
        if parent is None:
            active_components = loop.get_active_components()
            for active_component in reversed(active_components):
                if isinstance(active_component, Widget):
                    parent = active_component
                    break
        # -> we apply via set_parent below
        
        # Use parent session unless session was given
        if parent is not None and not kwargs.get('flx_session', None):
            kwargs['flx_session'] = parent.session
        
        # Allow initial styling via property-like mechanism
        style = kwargs.pop('style', '')
        
        # Whether this was the component that represents the app.
        # We use window.flexx.need_main_widget for a similar purpose,
        # but we might use it in the future.
        is_app = kwargs.get('flx_is_app', False)  # noqa
        
        # Init this component (e.g. create properties and actions)
        super().__init__(*init_args, **kwargs)
        
        # Some further initialization ...
        # Note that the _comp_init_property_values() will get called first.
        
        # Attach this widget in the widget hierarchy, if we can
        if parent is not None:
            # Just attach to the parent
            self.set_parent(parent)
        elif self.container == '':
            # Determine whether this should be the main widget. If the browser
            # seems to need one, and this is the first "orphan" widget to be 
            # instantiated, this widget will take on this role.
            if window.flexx.need_main_widget:
                window.flexx.need_main_widget = False
                self.set_container('body')
        
        # Invoke some actions
        if style:
            self.apply_style(style)
        self._check_min_max_size()
    
    def _comp_init_property_values(self, property_values):
        # This is a good time to do further initialization. The JsComponent
        # does its init here, property values have been set at this point,
        # but init() has not yet been called.
        
        prop_events = super()._comp_init_property_values(property_values)
        
        # Create DOM nodes
        # outernode is the root node
        # node is an inner (representative) node, often the same, but not always
        nodes = self._create_dom()
        assert nodes is not None
        if not isinstance(nodes, list):
            nodes = [nodes]
        assert len(nodes) == 1 or len(nodes) == 2
        if len(nodes) == 1:
            self.outernode = self.node = self.__render_resolve(nodes[0])
        else:
            self.outernode = self.__render_resolve(nodes[0])
            self.node = self.__render_resolve(nodes[1])
        
        # Derive css class name from class hierarchy (needs self.outernode)
        cls = self.__class__
        for i in range(32):  # i.e. a safe while-loop
            self.outernode.classList.add('flx-' + cls.__name__)
            if cls is Widget.prototype:
                break
            cls = cls._base_class
        else:
            raise RuntimeError('Error determining class names for %s' % self.id)
        
        # Setup JS events to enter Flexx' event system (needs self.node)
        self._init_events()
        
        return prop_events
    
    def init(self):
        """ Overload this to initialize a custom widget. When called, this
        widget is the current parent.
        """
        # The Component class already implement a stub, but we may like a more
        # specific docstring here.
        pass
    
    def _create_dom(self):
        """ Create DOM node(s) for this widget.
        
        This method must return two (real or virtual) DOM nodes which
        will be available as ``self.outernode`` and ``self.node``
        respectively. If a single node is given, it is used for both
        values. These attributes must remain unchanged throughout the
        lifetime of a widget. This method can be overloaded in
        subclasses.
        """
        return create_element('div')
    
    def _render_dom(self):
        """ Update the content of the DOM for this widget.
        
        This method must return a DOM structure that can consist of (a mix of)
        virtual nodes and real nodes. The widget will use this structure to
        update the real DOM in a relatively efficient manner (new nodes are
        only (re)created if needed). The root element must match the type of
        this widget's outernode. This method may also return a list or string
        to use as the root node's content.
        
        Note that this method is called from an implicit reaction: it will
        auto-connect to any properties that are accessed. Combined with the
        above, this allows for a very declarative way to write widgets.
        
        Virtual nodes are represented as dicts with fields "type", "props"
        and "children". Children may also be string to use as innerHTML.
        The ``create_element()`` function makes it easier to define nodes.
        
        The default ``_render_dom()`` method simply places the outer node of
        the child widgets as the content of this DOM node, while preserving
        nodes that do not represent a widget. Overload as needed.
        """
        nodes = []
        for i in range(len(self.outernode.children)):
            node = self.outernode.children[i]
            if not node.classList.contains('flx-Widget'):
                nodes.append(node)
        for widget in self.children:
            nodes.append(widget.outernode)
        return nodes
    
    @event.reaction
    def __render(self):
        # Call render method
        vnode = self._render_dom()
        # Validate output, allow it to return content instead of a vnode
        if vnode is None or vnode is self.outernode:
            return
        elif isinstance(vnode, str) or isinstance(vnode, list):
            vnode = dict(type=self.outernode.nodeName, props={}, children=vnode)
        elif isinstance(vnode, dict):
            if vnode.type.lower() != self.outernode.nodeName.lower():
                raise ValueError('Widget._render_dom() must return root node with '
                                 'same element type as outernode.')
        else:
            raise TypeError('Widget._render_dom() '
                            'must return None, str, list or dict.')
        # Resolve
        node = self.__render_resolve(vnode, self.outernode)
        assert node is self.outernode
    
    def __render_resolve(self, vnode, node=None):
        """ Given a DOM node and its virtual representation,
        update or create a new DOM node as necessary.
        """
        
        # Check vnode (we check vnode.children further down)
        if vnode and vnode.nodeName:  # is DOM node
            return vnode
        elif isinstance(vnode, str):
            vnode = {'type':'span', 'props':{}, 'children': vnode}
            # return window.document.createTextNode(vnode)  #  not in node.children
        elif not isinstance(vnode, dict):
            raise TypeError('Widget._render_dom() needs virtual nodes '
                            'to be dicts, not ' + vnode)
        if not isinstance(vnode.type, str):
            raise TypeError('Widget._render_dom() needs virtual node '
                            'type to be str, not ' + vnode.type)
        if not isinstance(vnode.props, dict):
            raise TypeError('Widget._render_dom() needs virtual node '
                            'props as dict, not ' + vnode.props)
        
        # Resolve the node itself
        if node is None or node.nodeName.lower() != vnode.type.lower():
            node = window.document.createElement(vnode.type)
        
        # Resolve props (i.e. attributes)
        map = {'css_class': 'className', 'class': 'className'}
        for key, val in vnode.props.items():
            ob = node
            parts = key.replace('__', '.').split('.')
            for i in range(len(parts)-1):
                ob = ob[parts[i]]
            key = parts[len(parts)-1]
            ob[map.get(key, key)] = val
        
        # Resolve content
        if vnode.children is None:
            pass  # dont touch it
        elif isinstance(vnode.children, str):
            node.innerHTML = vnode.children
        elif isinstance(vnode.children, list):
            # Truncate children
            while len(node.children) > len(vnode.children):
                node.removeChild(node.children[len(node.children)-1])
            # Resolve children
            i1 = -1
            for i2 in range(len(vnode.children)):
                i1 += 1
                vsubnode = vnode.children[i2]
                subnode = None
                if i1 < len(node.children):
                    subnode = node.children[i1]
                new_subnode = self.__render_resolve(vsubnode, subnode)
                if subnode is None:
                    node.appendChild(new_subnode)
                elif subnode is not new_subnode:
                    node.insertBefore(new_subnode, subnode)
                    node.removeChild(subnode)
        else:
            window.flexx_vnode = vnode
            raise TypeError('Widget._render_dom() '
                            'needs virtual node children to be str or list, not %s' %
                            vnode.children)
        
        return node
    
    # Note that this method is only present at the Python side
    # (because the JsComponent meta class makes it so).
    def _repr_html_(self):
        """ This is to get the widget shown inline in the notebook.
        """
        if self.container:
            return "<i>Th widget %s is already shown in this notebook</i>" % self.id

        container_id = self.id + '_container'
        self.set_container(container_id)
        return "<div class='flx-container' id='%s' />" % container_id

    def dispose(self):
        """ Overloaded version of dispose() that disposes any child widgets.
        """
        # Dispose children? Yes, each widget can have exactly one parent and
        # when that parent is disposed, it makes sense to assume that the
        # child ought to be disposed as well. It avoids memory leaks. If a
        # child is not supposed to be disposed, the developer should orphan the
        # child widget.
        children = self.children
        # First dispose children (so they wont send messages back), then clear
        # the children and dispose ourselves.
        for child in children:
            child.dispose()
        super().dispose()
        self.set_parent(None)
        self._children_value = ()
    
    ## Actions
    
    
    @event.action
    def apply_style(self, style):
        """ Apply CSS style to this widget object. e.g.
        ``"background: #f00; color: #0f0;"``. If the given value is a
        dict, its key-value pairs are converted to a CSS style string.
        
        Initial styling can also be given in a property-like fashion:
        ``MyWidget(style='background:red;')``
        
        For static styling it is often better to define a CSS class attribute
        and/or use ``css_class``.
        """
        if isinstance(style, dict):
            style = ['%s: %s' % (k, v) for k, v in style.items()]
            style = '; '.join(style)
        
        # self.node.style = style  # forbidden in strict mode,
        # plus it clears all previously set style

        # Note that styling is applied to the outer node, just like
        # the styling defined via the CSS attribute. In most cases
        # the inner and outer node are the same, but not always
        # (e.g. CanvasWidget).

        # Set style elements, keep track in a dict
        d = {}
        if style:
            for part in style.split(';'):
                if ':' in part:
                    key, val = part.split(':')
                    key, val = key.trim(), val.trim()
                    self.outernode.style[key] = val
                    d[key] = val

        # Did we change style related to sizing?
        size_limits_keys = 'min-width', 'min-height', 'max-width', 'max-height'
        size_limits_changed = False
        for key in size_limits_keys:
            if key in d:
                size_limits_changed = True
        
        if size_limits_changed:
            self._check_min_max_size()
    
    ## Reactions
    
    @event.reaction('css_class')
    def __css_class_changed(self, *events):
        if len(events):
            # Reset / apply explicitly given class name (via the prop)
            for cn in events[0].old_value.split(' '):
                if cn:
                    self.outernode.classList.remove(cn)
            for cn in events[-1].new_value.split(' '):
                if cn:
                    self.outernode.classList.add(cn)
    
    @event.reaction('title')
    def __title_changed(self, *events):
        if self.parent is None and self.container == 'body':
            window.document.title = self.title or 'Flexx app'
    
    @event.reaction('icon')
    def __icon_changed(self, *events):
        if self.parent is None and self.container == 'body':
            window.document.title = self.title or 'Flexx app'
            
            link = window.document.createElement('link')
            oldLink = window.document.getElementById('flexx-favicon')
            link.id = 'flexx-favicon'
            link.rel = 'shortcut icon'
            link.href = events[-1].new_value
            if oldLink:
                window.document.head.removeChild(oldLink)
            window.document.head.appendChild(link)
    
    @event.reaction
    def __update_tabindex(self, *events):
        # Note that this also makes the widget able to get focus, and thus
        # able to do key events.
        ti = self.tabindex
        if ti < -1:
            self.node.removeAttribute('tabIndex')
        else:
            self.node.tabIndex = ti
    
    # Now solved with CSS, which seems to work, but leaving this code for now ...
    # @event.reaction('children', '!children*.mode', '!children*.orientation')
    # def __make_singleton_container_widgets_work(self, *events):
    #     classNames = self.outernode.classList
    #     if not classNames.contains('flx-Layout'):
    #         # classNames.remove('flx-box')
    #         # classNames.remove('flx-horizontal')
    #         # classNames.remove('flx-vertical')
    #         classNames.remove('flx-abs-children')
    #         children = self.children
    #         if len(children) == 1:
    #             subClassNames = children[0].outernode.classList
    #             if subClassNames.contains('flx-Layout'):
    #                 classNames.add('flx-abs-children')
    #             # This seems to be enough, though previously we did:
    #             # if subClassNames.contains('flx-box'):
    #             #     # classNames.add('flx-box')
    #             #     vert = subClassNames.contains('flx-vertical')
    #             #     classNames.add('flx-horizontal' if vert else 'flx-horizontal')
    #             # else:
    #             #     # If child is a layout that uses absolute position, make
    #             #     # out children absolute.
    #             #     for name in ('split', 'StackPanel', 'TabPanel', 'DockPanel'):
    #             #         if subClassNames.contains('flx-' + name):
    #             #             classNames.add('flx-abs-children')
    #             #             break
    
    ## Sizing
    
    @event.action
    def check_real_size(self):
        """ Check whether the current size has changed. It should usually not
        be necessary to invoke this action, since a widget does so by itself,
        but it some situations the widget may not be aware of possible size
        changes.
        """
        n = self.outernode
        cursize = self.size
        if cursize[0] != n.clientWidth or cursize[1] != n.clientHeight:
            self._mutate_size([n.clientWidth, n.clientHeight])
    
    @event.action
    def _check_min_max_size(self):
        """ Query the minimum and maxium size.
        """
        mima = self._query_min_max_size()
        self._mutate_size_min_max(mima)
    
    def _query_min_max_size(self):
        # Query
        style = window.getComputedStyle(self.outernode)
        mima = [style.minWidth, style.maxWidth, style.minHeight, style.maxHeight]
        # Pixelize - we dont handle % or em or whatever
        for i in range(4):
            if mima[i] == '0':
                mima[i] = 0
            elif mima[i].endswith('px'):
                mima[i] = float(mima[i][:-2])
            else:
                mima[i] = 0 if (i == 0 or i == 2) else 1e9
        # Protect against min > max
        if mima[0] > mima[1]:
            mima[0] = mima[1] = 0.5 * (mima[0] + mima[1])
        if mima[2] > mima[3]:
            mima[2] = mima[3] = 0.5 * (mima[2] + mima[3])
        return mima
    
    @event.reaction('children', 'children*.size_min_max')
    def __min_max_size_may_have_changed(self, *events):
        self._check_min_max_size()
    
    @event.reaction('container', 'parent.size', 'children')
    def __size_may_have_changed(self, *events):
        # Invoke actions, i.e. check size in *next* event loop iter to
        # give the DOM a chance to settle.
        self.check_real_size()
    
    def _set_size(self, prefix, w, h):
        """ Method to allow setting size (via style). Used by some layouts.
        """
        size = w, h
        for i in range(2):
            if size[i] <= 0 or size is None or size is undefined:
                size[i] = ''  # Use size defined by CSS
            elif size[i] > 1:
                size[i] = size[i] + 'px'
            else:
                size[i] = size[i] * 100 + '%'
        self.outernode.style[prefix + 'width'] = size[0]
        self.outernode.style[prefix + 'height'] = size[1]
    
    ## Parenting
    
    @event.action
    def set_parent(self, parent, pos=None):
        """ Set the parent widget (can be None). This action also mutates the
        childen of the old and new parent.
        """
        old_parent = self.parent  # or None
        new_parent = parent
        
        # Early exit
        if new_parent is old_parent and pos is None:
            return
        if not (new_parent is None or isinstance(new_parent, Widget)):
            raise ValueError('%s.parent must be a Widget or None' % self.id)
        
        # Apply parent
        self._mutate_parent(new_parent)
        
        # Remove ourselves
        if old_parent is not None:
            children = list(old_parent.children)
            while self in children:
                children.remove(self)
            if old_parent is not new_parent:
                old_parent._mutate_children(children)
        
        # Insert ourselves
        if new_parent is not None:
            if old_parent is not new_parent: 
                children = list(new_parent.children)
            while self in children:
                children.remove(self)
            if pos is None:
                children.append(self)
            elif pos >= 0:
                children.insert(pos, self)
            elif pos < 0:
                children.append(None)
                children.insert(pos, self)
                children.pop(-1)
            else:  # maybe pos is nan for some reason
                children.append(None)
            new_parent._mutate_children(children)
    
    @event.reaction('container')
    def __container_changed(self, *events):
        id = self.container
        self.outernode.classList.remove('flx-main-widget')
        if self.parent:
            return
        
        # Let session keep us up to date about size changes
        self._session.keep_checking_size_of(self, bool(id))
        
        if id:
            if id == 'body':
                el = window.document.body
                self.outernode.classList.add('flx-main-widget')
                window.document.title = self.title or 'Flexx app'
            else:
                el = window.document.getElementById(id)
                if el is None:  # Try again later
                    print('conainer %s try again' % id)
                    window.setTimeout(self.__container_changed, 100)
                    return
                print('conainer %s worked!' % id)
            el.appendChild(self.outernode)
    
    def _release_child(self, widget):
        """ Overload to restore a child widget, e.g. to its normal style.
        """
        pass
    
    ## Events

    # todo: events: focus, enter, leave ... ?
    
    def _registered_reactions_hook(self):
        event_types = super()._registered_reactions_hook()
        if self.tabindex < -1:
            for event_type in event_types:
                if event_type in ('key_down', 'key_up', 'key_press'):
                    self.set_tabindex(-1)
        return event_types
    
    def _init_events(self):
        # Connect some standard events
        self._addEventListener(self.node, 'mousedown', self.mouse_down, 0)
        self._addEventListener(self.node, 'wheel', self.mouse_wheel, 0)
        self._addEventListener(self.node, 'keydown', self.key_down, 0)
        self._addEventListener(self.node, 'keyup', self.key_up, 0)
        self._addEventListener(self.node, 'keypress', self.key_press, 0)
        
        # Implement mouse capturing. When a mouse is pressed down on
        # a widget, it "captures" the mouse, and will continue to receive
        # move and up events, even if the mouse is not over the widget.

        self._capture_flag = 0
        # 0: mouse not down, 1: mouse down (no capture), 2: captured, -1: capture end
        
        def mdown(e):
            # Start emitting move events, maybe follow the mouse outside widget bounds
            if self.capture_mouse == 0:
                self._capture_flag = 1
            else:
                self._capture_flag = 2
                window.document.addEventListener("mousemove", mmove_outside, True)
                window.document.addEventListener("mouseup", mup_outside, True)
                # On FF, capture so we get events when outside browser viewport.
                # This seems not neccessary, but maybe it was on earlier versions?
                if self.node.setCapture:
                    self.node.setCapture()

        def mmove_inside(e):
            # maybe emit move event
            if self._capture_flag == -1:
                self._capture_flag = 0
            elif self._capture_flag == 1:
                self.mouse_move(e)
            elif self._capture_flag == 0 and self.capture_mouse > 1:
                self.mouse_move(e)
        
        def mup_inside(e):
            if self._capture_flag == 1:
                self.mouse_up(e)
            self._capture_flag = 0
        
        def mmove_outside(e):
            # emit move event
            if self._capture_flag == 2:  # can hardly be anything else, but be safe
                e = window.event if window.event else e
                self.mouse_move(e)
        
        def mup_outside(e):
            # emit mouse up event, and stop capturing
            if self._capture_flag == 2:
                e = window.event if window.event else e
                stopcapture()
                self.mouse_up(e)
        
        def stopcapture():
            # Stop capturing
            if self._capture_flag == 2:
                self._capture_flag = -1
                window.document.removeEventListener("mousemove", mmove_outside, True)
                window.document.removeEventListener("mouseup", mup_outside, True)
        
        def losecapture(e):
            # We lost the capture, emit mouse up to "drop" the target
            stopcapture()
            # self.mouse_up(e)  # mmm, better not
        
        # Setup capturing and releasing
        self._addEventListener(self.node, 'mousedown', mdown, True)
        self._addEventListener(self.node, "losecapture", losecapture)
        # Subscribe to normal mouse events
        self._addEventListener(self.node, "mousemove", mmove_inside, False)
        self._addEventListener(self.node, "mouseup", mup_inside, False)

    @event.emitter
    def mouse_down(self, e):
        """ Event emitted when the mouse is pressed down.

        A mouse event has the following attributes:

        * pos: the mouse position, in pixels, relative to this widget
        * page_pos: the mouse position relative to the page
        * button: what button the event is about, 1, 2, 3 are left, right,
            middle, respectively. 0 indicates no button.
        * buttons: what buttons where pressed at the time of the event.
        * modifiers: list of strings "Alt", "Shift", "Ctrl", "Meta" for
            modifier keys pressed down at the time of the event.
        """
        return self._create_mouse_event(e)

    @event.emitter
    def mouse_up(self, e):
        """ Event emitted when the mouse is pressed up.

        See mouse_down() for a description of the event object.
        """
        ev = self._create_mouse_event(e)
        return ev

    @event.emitter
    def mouse_move(self, e):
        """ Event fired when the mouse is moved inside the canvas.
        See mouse_down for details.
        """

        ev = self._create_mouse_event(e)
        ev.button = 0
        return ev

    @event.emitter
    def mouse_wheel(self, e):
        """ Event emitted when the mouse wheel is used.

        See mouse_down() for a description of the event object.
        Additional event attributes:

        * hscroll: amount of scrolling in horizontal direction
        * vscroll: amount of scrolling in vertical direction
        """
        # Note: wheel event gets generated also for parent widgets
        # I think this makes sense, but there might be cases
        # where we want to prevent propagation.
        ev = self._create_mouse_event(e)
        ev.button = 0
        ev.hscroll = e.deltaX * [1, 16, 600][e.deltaMode]
        ev.vscroll = e.deltaY * [1, 16, 600][e.deltaMode]
        return ev

    def _create_mouse_event(self, e):
        # note: our button has a value as in JS "which"
        modifiers = [n for n in ('Alt', 'Shift', 'Ctrl', 'Meta')
                        if e[n.lower()+'Key']]
        # Fix position
        pos = e.clientX, e.clientY
        rect = self.node.getBoundingClientRect()
        offset = rect.left, rect.top
        pos = float(pos[0] - offset[0]), float(pos[1] - offset[1])
        # Fix buttons
        if e.buttons:
            buttons_mask = reversed([c for c in e.buttons.toString(2)]).join('')
        else:
            # libjavascriptcoregtk-3.0-0  version 2.4.11-1 does not define
            # e.buttons
            buttons_mask = [e.button.toString(2)]
        buttons = [i+1 for i in range(5) if buttons_mask[i] == '1']
        button = {0: 1, 1: 3, 2: 2, 3: 4, 4: 5}[e.button]
        # Create event dict
        return dict(pos=pos, page_pos=(e.pageX, e.pageY),
                    button=button, buttons=buttons,
                    modifiers=modifiers,
                    )

    @event.emitter
    def key_down(self, e):
        """ Event emitted when a key is pressed down while this
        widget has focus. A key event has the following attributes:

        * key: the character corresponding to the key being pressed, or
            a key name like "Escape", "Alt", "Enter".
        * modifiers: list of strings "Alt", "Shift", "Ctrl", "Meta" for
            modifier keys pressed down at the time of the event.
        
        A browser may associate certain actions with certain key presses.
        If this browser action is unwanted, it can be disabled by
        overloading this emitter:
        
        .. code-block:: py
        
            @event.emitter
            def key_down(self, e):
                # Prevent browser's default reaction to function keys
                ev = super().key_press(e)
                if ev.key.startswith('F'):
                    e.preventDefault()
                return ev
        """
        return self._create_key_event(e)
    
    @event.emitter
    def key_up(self, e):
        """ Event emitted when a key is released while
        this widget has focus. See key_down for details.
        """
        return self._create_key_event(e)

    @event.emitter
    def key_press(self, e):
        """ Event emitted when a key is pressed down. This event does not
        fire for the pressing of a modifier keys. See key_down for details.
        """
        return self._create_key_event(e)

    def _create_key_event(self, e):
        # https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent
        # key: chrome 51, ff 23, ie 9
        # code: chrome ok, ff 32, ie no
        modifiers = [n for n in ('Alt', 'Shift', 'Ctrl', 'Meta')
                        if e[n.lower()+'Key']]
        key = e.key
        if not key and e.code:  # Chrome < v51
            key = e.code
            if key.startswith('Key'):
                key = key[3:]
                if 'Shift' not in modifiers:
                    key = key.lower()
            elif key.startswith('Digit'):
                key = key[5:]
        # todo: handle Safari and older browsers via keyCode
        key = {'Esc': 'Escape', 'Del': 'Delete'}.get(key, key)  # IE
        return dict(key=key, modifiers=modifiers)

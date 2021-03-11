"""
Configuration is used to control the behaviour of a system

Config can be passed as a dict, a filename from which a YAML spec is read in
and then parsed

There are no set elements for configurations, although typically they will
contain:

parameters - a dict of values which override those in system.defaults
trading_rules - a specification of the trading rules for a system

"""

import yaml
from syscore.fileutils import get_filename_for_package
from syscore.objects import missing_data, arg_not_supplied
from systems.defaults import get_system_defaults_dict
from syslogdiag.log import logtoscreen
from sysdata.config.fill_config_dict_with_defaults import fill_config_dict_with_defaults

RESERVED_NAMES = ["log", "_elements", "elements", "_default_filename", "_default_dict"]


class Config(object):
    def __init__(self, config_object=arg_not_supplied,
                 default_filename = arg_not_supplied):
        """
        Config objects control the behaviour of systems

        :param config_object: Either:
                        a string (which points to a YAML filename)
                        or a dict (which may nest many things)
                        or a list of strings or dicts (build config from
                        multiple elements, latter elements will overwrite
                        earlier oness)

        :type config_object: str or dict

        :returns: new Config object

        >>> Config(dict(parameters=dict(p1=3, p2=4.6), another_thing=[]))
        Config with elements: another_thing, parameters

        >>> Config("sysdata.tests.exampleconfig.yaml")
        Config with elements: parameters, trading_rules

        >>> Config(["sysdata.tests.exampleconfig.yaml", dict(parameters=dict(p1=3, p2=4.6), another_thing=[])])
        Config with elements: another_thing, parameters, trading_rules

        """

        # this will normally be overriden by the base system
        self.log= logtoscreen(type="config", stage="config")

        self._default_filename = default_filename

        if config_object is arg_not_supplied:
            config_object = dict()

        if isinstance(config_object, list):
            # multiple configs
            config_list = config_object
        else:
            config_list = [config_object]

        self._create_config_from_list(config_list)


    @property
    def elements(self) -> list:
        elements = getattr(self, "_elements", [])

        return elements


    def add_elements(self, new_elements: list):
        _ = [self.add_single_element(element_name) for element_name in new_elements]

    def remove_element(self, element: str):
        current_elements = self.elements
        current_elements.remove(element)
        self._elements = current_elements

    def add_single_element(self, element_name):
        if element_name not in RESERVED_NAMES:
            elements = self.elements
            if element_name not in elements:
                elements.append(element_name)
                self._elements = elements

    def get_element_or_missing_data(self, element_name):
        result = getattr(self, element_name, missing_data)
        return result

    def get_element_or_arg_not_supplied(self, element_name):
        result = getattr(self, element_name, arg_not_supplied)
        return  result

    def __repr__(self):
        elements = self.elements
        elements.sort()
        return "Config with elements: %s" % ", ".join(self.elements)

    def _create_config_from_list(self, config_object):
        for config_item in config_object:
            self._create_config_from_item(config_item)

    def _create_config_from_item(self, config_item):
        if isinstance(config_item, dict):
            # its a dict
            self._create_config_from_dict(config_item)

        elif isinstance(config_item, str):
            # must be a file YAML'able, from which we load the
            filename = get_filename_for_package(config_item)
            with open(filename) as file_to_parse:
                dict_to_parse = yaml.load(
                    file_to_parse, Loader=yaml.FullLoader)

            self._create_config_from_dict(dict_to_parse)

        else:
            error_msg = (
                "Can only create a config with a nested dict or the "
                "string of a 'yamable' filename, or a list "
                "comprising these things"
            )
            self.log.critical(error_msg)

    def _create_config_from_dict(self, config_object):
        """
        Take a dictionary object and turn it into self

        When we've finished self will be an object where the attributes are

        So if config_objec=dict(a=2, b=2)
        Then this object will become self.a=2, self.b=2
        """
        base_config = config_object.get("base_config")
        if base_config is not None:
            self._create_config_from_item(base_config)

        attr_names = list(config_object.keys())
        [setattr(self, keyname, config_object[keyname])
         for keyname in config_object]

        self.add_elements(attr_names)

    def system_init(self, base_system):
        """
        This is run when added to a base system

        :param base_system
        :return: nothing
        """

        # inherit the log
        setattr(self, "log", base_system.log.setup(stage="config"))

        # fill with defaults
        self.fill_with_defaults()

    def __delattr__(self, element_name: str):
        """
        Remove element_name from config

        >>> config=Config(dict(parameters=dict(p1=3, p2=4.6), another_thing=[]))
        >>> del(config.another_thing)
        >>> config
        Config with elements: parameters
        >>>
        """
        # to avoid recursion, we must first avoid recursion
        super().__delattr__(element_name)

        self.remove_element(element_name)

    def __setattr__(self, element_name:str, value):
        """
        Add / replace element_name in config

        >>> config=Config(dict(parameters=dict(p1=3, p2=4.6), another_thing=[]))
        >>> config.another_thing="test"
        >>> config.another_thing
        'test'
        >>> config.yet_another_thing="more testing"
        >>> config
        Config with elements: another_thing, parameters, yet_another_thing
        >>>
        """
        # to avoid recursion, we must first avoid recursion
        super().__setattr__(element_name, value)
        self.add_single_element(element_name)

    def fill_with_defaults(self):
        """
        Fills with defaults
        >>> config=Config(dict(forecast_cap=22.0, forecast_scalar_estimate=dict(backfill=False), forecast_weight_estimate=dict(correlation_estimate=dict(min_periods=40))))
        >>> config
        Config with elements: forecast_cap, forecast_scalar_estimate, forecast_weight_estimate
        >>> config.fill_with_defaults()
        >>> config.forecast_scalar
        1.0
        >>> config.forecast_cap
        22.0
        >>> config.forecast_scalar_estimate['pool_instruments']
        True
        >>> config.forecast_scalar_estimate['backfill']
        False
        >>> config.forecast_weight_estimate['correlation_estimate']['min_periods']
        40
        >>> config.forecast_weight_estimate['correlation_estimate']['ew_lookback']
        500
        """
        self.log.msg("Adding config defaults")

        self_as_dict = self.as_dict()
        defaults_dict = self._default_config_dict()

        new_dict = fill_config_dict_with_defaults(self_as_dict, defaults_dict)

        self._create_config_from_dict(new_dict)

    # clean up
    def _default_config_dict(self) -> dict:
        default_dict = getattr(self, "_default_dict", arg_not_supplied)
        if default_dict is arg_not_supplied:
            default_filename = self._default_config_filename()
            default_dict = get_system_defaults_dict(filename=default_filename)
            self._default_dict = default_dict

        return default_dict

    def _default_config_filename(self) -> str:
        default_filename = getattr(self, "_default_filename", arg_not_supplied)

        return default_filename

    def as_dict(self):
        element_names = sorted(getattr(self, "_elements", []))
        self_as_dict = {}
        for element in element_names:
            self_as_dict[element] = getattr(self, element, "")

        return self_as_dict

    def save(self, filename):
        config_to_save = self.as_dict()
        with open(filename, "w") as file:
            yaml.dump(config_to_save, file)


if __name__ == "__main__":
    import doctest

    doctest.testmod()

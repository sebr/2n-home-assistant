"""Config flow for the 2N Intercom integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.httpx_client import get_async_client

from .const import (
    CONF_LOCK_SWITCHES,
    CONF_SCAN_INTERVAL,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    LOGGER,
)
from .hapi.api import TwoNApiClient
from .hapi.exceptions import (
    TwoNAuthError,
    TwoNConnectionError,
    TwoNError,
    TwoNPrivilegeError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.config_entries import ConfigFlowResult

    from .hapi.models import SystemInfo


class TwoNFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for a 2N intercom."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        _config_entry: config_entries.ConfigEntry,
    ) -> TwoNOptionsFlowHandler:
        """Get the options flow for this handler."""
        return TwoNOptionsFlowHandler()

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            if not host.startswith(("http://", "https://")):
                # The device's HTTP API services default to HTTPS.
                host = f"https://{host}"
            cleaned_input = {**user_input, CONF_HOST: host}
            try:
                info = await self._validate(cleaned_input)
            except TwoNAuthError as exception:
                LOGGER.warning(exception)
                errors["base"] = "invalid_auth"
            except TwoNConnectionError as exception:
                LOGGER.error(exception)
                errors["base"] = "cannot_connect"
            except TwoNError as exception:
                LOGGER.exception(exception)
                errors["base"] = "unknown"
            else:
                unique_id = info.serial_number or info.mac_addr
                if unique_id:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                else:
                    # No serial/MAC available (restricted account or old
                    # firmware); fall back to the host to block duplicates.
                    self._async_abort_entries_match(
                        {CONF_HOST: cleaned_input[CONF_HOST]}
                    )
                return self.async_create_entry(
                    title=info.device_name or "2N Intercom",
                    data=cleaned_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=(user_input or {}).get(CONF_HOST, vol.UNDEFINED),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.URL,
                        ),
                    ),
                    vol.Required(
                        CONF_USERNAME,
                        default=(user_input or {}).get(CONF_USERNAME, vol.UNDEFINED),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                        ),
                    ),
                    vol.Required(
                        CONF_PASSWORD,
                        default=(user_input or {}).get(CONF_PASSWORD, vol.UNDEFINED),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        ),
                    ),
                    vol.Required(
                        CONF_VERIFY_SSL,
                        default=(user_input or {}).get(
                            CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL
                        ),
                    ): selector.BooleanSelector(),
                },
            ),
            errors=errors,
        )

    async def _validate(self, data: dict[str, Any]) -> SystemInfo:
        """Check connectivity and credentials; return the device info."""
        client = TwoNApiClient(
            host=data[CONF_HOST],
            username=data[CONF_USERNAME],
            password=data[CONF_PASSWORD],
            client=get_async_client(
                self.hass, verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
            ),
        )
        info = await client.get_system_info()
        # /api/system/info may be accessible without credentials, so also hit
        # an authenticated endpoint to verify them. A privilege error still
        # proves the credentials themselves are valid.
        try:
            await client.get_system_status()
        except TwoNPrivilegeError:
            LOGGER.debug("Account lacks system monitoring privilege; continuing")
        except TwoNError as err:
            # Endpoint disabled on the device is fine; only auth failures and
            # connection problems should block the flow.
            if isinstance(err, (TwoNAuthError, TwoNConnectionError)):
                raise
            LOGGER.debug("System status probe failed: %s", err)
        return info

    async def async_step_reauth(
        self,
        _entry_data: Mapping[str, Any],
    ) -> ConfigFlowResult:
        """Triggered when Home Assistant requests re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict | None = None,
    ) -> ConfigFlowResult:
        """Prompt the user for new credentials for the existing entry."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            try:
                await self._validate({**entry.data, **user_input})
            except TwoNAuthError as exception:
                LOGGER.warning(exception)
                errors["base"] = "invalid_auth"
            except TwoNConnectionError as exception:
                LOGGER.error(exception)
                errors["base"] = "cannot_connect"
            except TwoNError as exception:
                LOGGER.exception(exception)
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=user_input,
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=entry.data.get(CONF_USERNAME, vol.UNDEFINED),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                        ),
                    ),
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        ),
                    ),
                },
            ),
            description_placeholders={"name": entry.title},
            errors=errors,
        )


class TwoNOptionsFlowHandler(OptionsFlow):
    """Handle options flow for the 2N Intercom integration."""

    async def async_step_init(
        self,
        user_input: dict | None = None,
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        coordinator = getattr(self.config_entry, "runtime_data", None)
        switch_options = [
            selector.SelectOptionDict(
                value=str(caps.switch), label=f"Switch {caps.switch}"
            )
            for caps in (coordinator.switch_caps if coordinator else [])
            if caps.enabled
        ]

        schema: dict[Any, Any] = {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=self.config_entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=5,
                    max=300,
                    step=5,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.SLIDER,
                ),
            ),
        }
        if switch_options:
            schema[
                vol.Required(
                    CONF_LOCK_SWITCHES,
                    default=self.config_entry.options.get(
                        CONF_LOCK_SWITCHES,
                        [option["value"] for option in switch_options],
                    ),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=switch_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                ),
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
        )

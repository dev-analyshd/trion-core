// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/**
 * @title  MockTRIONToken
 * @notice Simple ERC-20 token used as the underlying asset for ConfidentialCoherenceVault.
 *         Freely mintable — for testnet demonstration only.
 * @author TRION Protocol | CC0 2026
 */
contract MockTRIONToken is ERC20 {
    constructor() ERC20("TRION Protocol Token", "TRIONt") {
        _mint(msg.sender, 10_000_000 * 10 ** 18);
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
